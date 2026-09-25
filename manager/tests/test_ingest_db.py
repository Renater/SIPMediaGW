"""
Ingestion against a real database.

Everything else in this suite replaces the database with a recorder, which
proves the code runs and says nothing about whether the schema agrees with it.
This file does the other half: it pushes a real payload through the route, lets
the trigger classify it, reads the row back, and removes it.

It needs a database and skips without one:

    DATABASE_URL_TEST=postgresql://gw_manager:PASS@127.0.0.1:5432/gw_manager \
        ./tools/test.sh tests/test_ingest_db.py -v

Pointed at the lab database, it leaves nothing behind: the pushed call carries
a marker in its id and is deleted at the end, success or not.
"""

import copy
import json
import os
from pathlib import Path

import pytest

DSN = os.getenv("DATABASE_URL_TEST")
MARKER = "test-ingest-db"

pytestmark = pytest.mark.skipif(not DSN, reason="DATABASE_URL_TEST not set; needs a real database")


@pytest.fixture()
def client(monkeypatch):
    """The real route, the real database, a known token."""
    from fastapi.testclient import TestClient
    import db
    import ingest.router as router
    import app as application

    monkeypatch.setattr(db, "databaseUrl", DSN)
    monkeypatch.setattr(db, "_pool", None)
    monkeypatch.setattr(router, "ingestToken", "test-token")
    yield TestClient(application.app)

    import psycopg
    with psycopg.connect(DSN) as conn, conn.cursor() as cursor:
        cursor.execute("DELETE FROM calls WHERE call_id LIKE %s", (f"{MARKER}%",))
        conn.commit()


def payload():
    """The fixture the mapping tests use, with a marker stamped into its id."""
    data = copy.deepcopy(json.loads((Path(__file__).parent / "fixtures" / "payload.json").read_text()))
    data["call"]["details"]["callId"] = f"{MARKER}-{os.getpid()}"
    return data


def push(client, data):
    return client.post("/ingest/calls", json=data,
                       headers={"Authorization": "Bearer test-token"})


def test_a_pushed_call_is_stored_and_classified(client):
    """
    The pipeline end to end: route, mapping, INSERT, trigger. The outcome is
    read back rather than assumed — it is the trigger's decision, made in the
    database, and the recorder-based tests never see it run.
    """
    import psycopg
    data = payload()
    response = push(client, data)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["stored"] is True

    with psycopg.connect(DSN) as conn, conn.cursor() as cursor:
        cursor.execute("""
            SELECT outcome, duration_s, occupancy_s, room,
                   (SELECT count(*) FROM call_media_stats WHERE call_pk = calls.id)
              FROM calls WHERE id = %s
        """, (body["call_pk"],))
        outcome, duration, occupancy, room, mediaRows = cursor.fetchone()

    assert outcome in ("completed", "failed", "ivr_only")
    if room:
        assert outcome == "completed", "a call that reached a room completed"
    assert occupancy >= duration, "gateway time includes what the call does not"
    assert mediaRows == body["media_rows"], "media rows stored must match those reported"


def test_a_replayed_push_is_ignored(client):
    """
    A gateway may push the same call twice — a retry after a timeout. The
    second push is acknowledged and stores nothing: the replay guard is a
    database constraint, and only a database can prove it holds.
    """
    data = payload()
    first = push(client, data)
    second = push(client, data)
    assert first.status_code == 200 and first.json()["stored"] is True
    assert second.status_code == 200 and second.json()["stored"] is False
    assert second.json()["status"] == "duplicate"


def test_recompute_org_units_is_callable(client):
    """
    The zero-argument call is what the sample rules file tells operators to
    run; two definitions with different signatures once made it ambiguous
    ("function recompute_org_units() is not unique"). It has to run.
    """
    import psycopg

    with psycopg.connect(DSN) as connection:
        rows = connection.execute("SELECT * FROM recompute_org_units()").fetchall()
        signatures = connection.execute(
            "SELECT count(*) FROM pg_proc WHERE proname = 'recompute_org_units'").fetchone()[0]
    assert len(rows) == 1
    assert signatures == 1, f"{signatures} definitions of recompute_org_units"


def fixture(name):
    data = json.loads((Path(__file__).parent / "fixtures" / name).read_text())
    data["call"]["details"]["callId"] = f"{MARKER}-{name}-{os.getpid()}"
    return data


def test_a_call_that_never_came_up_is_kept_and_counted(client):
    """
    A Call-ID without a start: stored, dated by its reception, classified
    not_established by the trigger, and its replay absorbed by the Call-ID.
    """
    import psycopg
    data = fixture("payload_not_established.json")
    first = push(client, data)
    assert first.status_code == 200 and first.json()["stored"] is True, first.text
    second = push(client, data)
    assert second.json()["stored"] is False, "a replay of a call without start is absorbed"

    with psycopg.connect(DSN) as conn, conn.cursor() as cursor:
        cursor.execute("""
            SELECT established, outcome, call_start = received_at, duration_s, gw_version
              FROM calls WHERE id = %s""", (first.json()["call_pk"],))
        established, outcome, datedByReception, duration, version = cursor.fetchone()
    assert established is False and outcome == "not_established"
    assert datedByReception and duration == 0
    assert version == "v1.8.9-71-gb06bc8f"


def test_the_new_fields_reach_their_columns(client):
    import psycopg
    response = push(client, fixture("payload_presentation.json"))
    assert response.status_code == 200, response.text
    assert response.json()["media_rows"] == 6, "audio 2 + the last video pair 4"

    with psycopg.connect(DSN) as conn, conn.cursor() as cursor:
        cursor.execute("""
            SELECT established, peer_user_agent, video_codec, media_direction->>'video',
                   baresip_patch, video_state, presentation_s, video_keyframe_requests
              FROM calls WHERE id = %s""", (response.json()["call_pk"],))
        row = cursor.fetchone()
    assert row[0] is True
    assert row[1].endswith("Cisco-RoomKitMini") and row[2] == "H264" and row[3] == "sendrecv"
    assert row[4] == "v3.15.0_patchv5" and row[5] == "ok"
    assert 120 <= row[6] <= 140 and row[7] == 80


def test_an_old_payload_is_still_accepted(client):
    """Pushed by a gateway without #101/#102/#105: stored, new columns NULL."""
    import psycopg
    response = push(client, fixture("payload_before_media.json"))
    assert response.status_code == 200, response.text
    with psycopg.connect(DSN) as conn, conn.cursor() as cursor:
        cursor.execute("SELECT peer_user_agent, gw_version, video_state, established FROM calls WHERE id = %s",
                       (response.json()["call_pk"],))
        assert cursor.fetchone() == (None, None, None, True)
