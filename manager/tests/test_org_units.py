"""
P22: entities and the rules that classify a calling endpoint.

Rules match the caller only (SIP URI, alias), literally and without regard
to case, by prefix or suffix. The list is read top to bottom and the
last rule that matches decides. Every change is written to org_unit_audit in
the same statement as the change.

Route tests run on the recorder (no database); the SQL functions are read as
text, and checked on a real database when DATABASE_URL_TEST is set.
"""

import os
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
SCHEMA = (ROOT / "db" / "schema_org_units.sql").read_text()
LOT0 = (ROOT / "db" / "schema_reporting_lot0.sql").read_text()

RULE = {"org_unit_code": "LAB", "field": "uri", "match_type": "suffix",
        "pattern": "@sample.org", "description": "city domain"}


# ------------------------------------------------------------ the rules, as SQL

def body(text, marker):
    start = text.index(marker)
    return text[start:text.index("$$;", start)]


def test_the_last_matching_rule_decides():
    resolve = body(SCHEMA, "CREATE OR REPLACE FUNCTION resolve_org_unit")
    assert "ORDER BY r.position DESC" in resolve and "LIMIT 1" in resolve
    assert "priority" not in resolve, "the old first-match order must not survive"


def test_a_prefix_is_a_prefix_and_case_does_not_count():
    """"1test" does not start with "test" (literal: no LIKE, no wildcard), and
    ABC = aBc (both sides lowered)."""
    matches = body(SCHEMA, "CREATE OR REPLACE FUNCTION org_unit_rule_matches")
    assert "WHEN 'prefix' THEN starts_with(lower(p_value), lower(p_pattern))" in matches
    assert "WHEN 'suffix' THEN right(lower(p_value), length(p_pattern)) = lower(p_pattern)" in matches
    assert "LIKE" not in matches.upper().replace("ILIKE", "")


def test_two_caller_fields_uri_and_alias():
    """A number is a URI prefix, a domain a URI suffix: the three old fields
    are converted, a domain prefix becoming the exact domain behind "@"."""
    assert "CHECK (field IN ('uri', 'alias'))" in SCHEMA
    assert "SET field = 'uri', match_type = 'suffix', pattern = '@' || pattern" in SCHEMA
    uri = body(SCHEMA, "CREATE OR REPLACE FUNCTION org_unit_uri")
    assert "'^sips?:'" in uri, "the scheme is not part of what rules match"


def test_only_the_caller_is_classified():
    """peer_display_name is the called side: it never names the caller."""
    trigger = body(SCHEMA, "CREATE OR REPLACE FUNCTION calls_set_org_unit")
    recompute = body(LOT0, "CREATE OR REPLACE FUNCTION recompute_org_units")
    for sql in (trigger, recompute):
        assert "resolve_org_unit(" in sql and "org_unit_uri(" in sql
        assert "peer_display_name" not in sql
        assert "source_name" in sql


def test_the_old_order_is_kept_when_positions_are_first_given():
    """Before P22 the longest pattern won; numbered from the shortest up, the
    last-match rule decides the same way. Only rules without a position, once."""
    update = SCHEMA[SCHEMA.index("UPDATE org_unit_rules r SET position"):]
    update = update[:update.index(";")]
    assert "length(pattern)" in update and "priority DESC" in update
    assert "r.position IS NULL" in update


# ------------------------------------------------------------------ the routes

def test_a_rule_is_written_with_its_audit_line(client):  # noqa: F811
    # The entity exists, no identical rule, then the write answers.
    client.recorder.queue = [[{"exists": 1}], [], [{"id": 7, "org_unit_code": "LAB"}]]
    response = client.post("/api/org-unit-rules", json=RULE)
    assert response.status_code == 201, response.text
    query, params = client.recorder.calls[-1]
    assert "INSERT INTO org_unit_rules" in query and "INSERT INTO org_unit_audit" in query
    assert "'rule_create'" in query and "test" in params, "the actor is the signed-in user"


@pytest.mark.parametrize("change, reason", [
    ({"match_type": "regex"}, "match_type"),
    ({"field": "peer"}, "field"),
    ({"field": "domain"}, "field"),
    ({"pattern": " sample.org"}, "space"),
    ({"pattern": "sample.org "}, "space"),
    ({"pattern": ""}, "pattern is required"),
    ({"description": ""}, "description is required"),
])
def test_a_loose_rule_is_refused(client, change, reason):  # noqa: F811
    """Rigid on purpose: nothing is trimmed or guessed, a regex is not written."""
    response = client.post("/api/org-unit-rules", json={**RULE, **change})
    assert response.status_code == 400 and reason in response.json()["detail"]


def test_the_same_rule_twice_is_refused(client):  # noqa: F811
    client.recorder.rows = [{"id": 3}]
    response = client.post("/api/org-unit-rules", json=RULE)
    assert response.status_code == 409 and "rule 3" in response.json()["detail"]


def test_a_deleted_rule_leaves_its_line(client):  # noqa: F811
    client.recorder.rows = [{"id": 5}]
    assert client.delete("/api/org-unit-rules/5").status_code == 200
    query, params = client.recorder.calls[-1]
    assert "DELETE FROM org_unit_rules" in query and "'rule_delete'" in query
    client.recorder.rows = []
    assert client.delete("/api/org-unit-rules/5").status_code == 404


def test_the_order_is_the_whole_list(client):  # noqa: F811
    """A partial or stale list is refused: the order is what decides."""
    client.recorder.rows = [{"id": 1}, {"id": 2}]
    assert client.put("/api/org-unit-rules-order", json={"ids": [1]}).status_code == 409
    assert client.put("/api/org-unit-rules-order", json={"ids": [2, 2]}).status_code == 409
    response = client.put("/api/org-unit-rules-order", json={"ids": [2, 1]})
    assert response.status_code == 200
    query, params = client.recorder.calls[-1]
    assert "'rules_order'" in query and [2, 1] in params


def test_the_probe_names_the_last_match(client):  # noqa: F811
    client.recorder.rows = [
        {"id": 1, "org_unit_code": "SALES", "position": 2, "unit_active": True},
        {"id": 6, "org_unit_code": "SAMPLE", "position": 6, "unit_active": True},
        {"id": 9, "org_unit_code": "OLD", "position": 9, "unit_active": False},
    ]
    body = client.post("/api/org-unit-rules/test", json={"uri": "sip:21001@sample.org", "alias": "Room"}).json()
    assert body["winner"]["id"] == 6, "an inactive entity decides nothing"
    assert len(body["matches"]) == 3


def test_reclassifying_the_history_is_logged(client):  # noqa: F811
    client.recorder.rows = [{"rows_seen": 10, "rows_moved": 2}]
    assert client.post("/api/org-units/recompute").json()["rows_moved"] == 2
    query, _ = client.recorder.calls[-1]
    assert "recompute_org_units(" in query and "'recompute'" in query


def test_an_entity_code_is_a_code(client):  # noqa: F811
    client.recorder.rows = []
    assert client.post("/api/org-units", json={"code": "bad code", "label": "x"}).status_code == 400
    assert client.post("/api/org-units", json={"code": "OK", "label": " x"}).status_code == 400


def test_the_entity_screen_is_for_administrators(monkeypatch):
    from fastapi.testclient import TestClient
    import app as application
    anonymous = TestClient(application.app)
    assert anonymous.get("/api/org-units").status_code == 401
    assert anonymous.post("/api/org-unit-rules", json=RULE).status_code == 401
    assert anonymous.delete("/api/org-unit-rules/1").status_code == 401
    assert anonymous.post("/api/org-units/recompute").status_code == 401


# ------------------------------------------------------- on a real database

DSN = os.getenv("DATABASE_URL_TEST")


@pytest.mark.skipif(not DSN, reason="DATABASE_URL_TEST not set; needs a real database")
def test_matching_on_the_database():
    """The functions themselves, read-only: nothing is written."""
    import psycopg
    cases = [
        ("prefix", "test", "test12", True), ("prefix", "test", "1test", False),
        ("prefix", "Room", "room 1", True), ("suffix", "@sample.org", "x@sample.org", True),
        ("suffix", "sample.org", "X@CITY.SAMPLE.ORG", True), ("prefix", "ACME_", "ACMEX", False),
        ("suffix", "fr", None, False),
    ]
    with psycopg.connect(DSN) as conn:
        for kind, pattern, value, expected in cases:
            got = conn.execute("SELECT org_unit_rule_matches(%s, %s, %s)", (kind, pattern, value)).fetchone()[0]
            assert bool(got) is expected, (kind, pattern, value)


# ------------------------------------------------------------ the audit log

def test_one_audit_log_for_accounts_and_entities(client):  # noqa: F811
    """Each line says its type; both tables are read, or only the one asked."""
    client.recorder.rows = []
    body = client.get("/api/audit").json()
    assert body["total"] == 0 and body["lines"] == []
    query, params = client.recorder.calls[-1]
    assert "FROM user_audit" in query and "FROM org_unit_audit" in query
    assert "'user' AS type" in query and "'entity' AS type" in query
    assert params[:2] == (True, True)
    client.get("/api/audit", params={"types": "entity"})
    assert client.recorder.calls[-1][1][:2] == (False, True)
    assert client.get("/api/audit", params={"types": "user,nope"}).status_code == 400
    assert client.get("/api/audit", params={"types": ""}).status_code == 400


def test_the_audit_is_searched_by_person_over_a_window_a_page_at_a_time(client):  # noqa: F811
    """Who acted or on whom; `%` typed in the box matches itself; dates and
    page reach the query; a reversed window is the client's mistake."""
    client.recorder.rows = [{"type": "user", "at": "2026-09-24T10:00:00+00:00", "actor": "toto",
                             "action": "update", "target": "bob@x.fr", "detail": {}, "total": 73}]
    body = client.get("/api/audit", params={"q": "to%to", "start": "2026-09-01T00:00:00",
                                            "end": "2026-09-24T23:59:59", "limit": 50, "offset": 50}).json()
    assert body["total"] == 73 and body["offset"] == 50 and "total" not in body["lines"][0]
    query, params = client.recorder.calls[-1]
    assert "actor ILIKE %s OR target ILIKE %s" in query
    assert "%to\\%to%" in params, params
    assert params[-2:] == (50, 50)
    assert str(params[2]).startswith("2026-09-01") and str(params[3]).startswith("2026-09-24")
    reversed_ = client.get("/api/audit", params={"start": "2026-09-24T00:00:00", "end": "2026-09-01T00:00:00"})
    assert reversed_.status_code == 400


def test_the_audit_has_its_own_tab():
    views = ROOT / "front" / "views"
    for page in ("users.html", "orgunits.html", "audit.html"):
        text = (views / page).read_text()
        assert 'data-subview="audit"' in text and 'data-subview="orgunits"' in text, page
    assert "ouAudit" not in (views / "orgunits.html").read_text(), "the audit left the entity screen"
    audit = (views / "audit.html").read_text()
    for control in ("auditPreset", "auditFrom", "auditTo", "auditSearch", "auditPrev", "auditNext"):
        assert f'id="{control}"' in audit, control
    main = (ROOT / "front" / "js" / "main.js").read_text()
    assert "['users', 'orgunits', 'audit'].includes(name) && context.role !== 'admin'" in main


def test_a_rule_shows_its_id_and_its_position():
    """The id never changes; the position does when the list is reordered."""
    i18n = (ROOT / "front" / "js" / "i18n.js").read_text()
    for columns in re.findall(r"ouRuleCols: \[([^\]]*)\]", i18n):
        names = re.findall(r"'([^']*)'", columns)
        assert names[0] == "ID" and names[-2] == "Position", names
    view = (ROOT / "front" / "js" / "views" / "orgunits.js").read_text()
    assert '<td class="center num">${esc(rule.id)}</td>' in view
    assert '<td class="center num">${index + 1}</td>' in view
    assert "tag ${" not in view, "states are words, not colours"
