"""
Call-history ingestion: the endpoint gateways push to at end of call
(logParse.py, LOG_PUSH_URL).

Replaces the standalone collector. Differences that matter:
  * a shared token is required (the collector accepted any POST);
  * video statistics are stored, not dropped;
  * a replayed push is absorbed instead of counted twice;
  * the raw payload is kept in JSONB, so a mapping gap can be repaired
    afterwards without having lost anything.
"""

import hmac
import json
import logging
import os
from typing import NoReturn

from fastapi import APIRouter, HTTPException, Request
from psycopg.types.json import Jsonb
from starlette.concurrency import run_in_threadpool

from db import connection

from ingest.mapping import callRow, mediaRows

router = APIRouter()
log = logging.getLogger("manager.ingest")

ingestToken = os.getenv("INGEST_TOKEN", "")

# A push without samples is a few kilobytes; with the periodic samples
# (SIPMediaGW #101) it grows by about 60 bytes a second, so 1 MB stopped at
# about 4 h 30 of call, less than a room left connected all day. 8 MB covers
# more than a day. It still bounds what a compromised gateway, which holds
# the token, can make the Manager read.
MAX_BODY_BYTES = int(os.getenv("INGEST_MAX_BODY_BYTES", str(8 * 1024 * 1024)))

CALL_COLUMNS = (
    "call_id", "gw_alias", "gw_id", "gw_host",
    "main_app", "platform", "room", "call_url",
    "source_uri", "source_name", "source_number", "source_domain",
    "destination_uri", "destination_room", "destination_domain", "peer_display_name",
    "call_start", "call_end", "duration_s", "occupancy_s",
    "close_reason", "last_event_type",
    "peer_user_agent", "audio_codec", "video_codec", "video_encoder",
    "gw_version", "baresip_version", "baresip_patch", "chromium_version",
    "video_state", "video_min_rx_fps", "video_low_intervals",
    "video_keyframe_requests", "presentation_s",
)

# Built once, from the constant above: no request reaches this text.
INSERT_CALL = f"""
    INSERT INTO calls ({', '.join(CALL_COLUMNS)}, media_direction, dtmf_events, raw)
    VALUES ({', '.join('%s' for _ in CALL_COLUMNS)}, %s, %s, %s)
    ON CONFLICT DO NOTHING
    RETURNING id
"""  # nosec B608  # column names from CALL_COLUMNS

INSERT_MEDIA = """
    INSERT INTO call_media_stats
        (call_pk, media, stream_index, direction, packets, errors,
         packet_reports, avg_bitrate_kbps, lost_packets, jitter_ms)
    VALUES (%(call_pk)s, %(media)s, %(stream_index)s, %(direction)s, %(packets)s,
            %(errors)s, %(packet_reports)s, %(avg_bitrate_kbps)s,
            %(lost_packets)s, %(jitter_ms)s)
    ON CONFLICT DO NOTHING
"""


def authorizeIngest(request: Request) -> bool:
    """Unset INGEST_TOKEN closes the route, as elsewhere in this codebase."""
    if not ingestToken:
        return False
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        return False
    # As bytes: compare_digest refuses a str with non-ASCII characters, which
    # a client could send to turn a 401 into a 500.
    return hmac.compare_digest(header.split(" ", 1)[1].encode(), ingestToken.encode())


def tooLarge(request: Request, size: int):
    client = request.client.host if request.client else "?"
    log.warning("push refused: %d bytes, limit %d (INGEST_MAX_BODY_BYTES), from %s",
                size, MAX_BODY_BYTES, client)
    raise HTTPException(status_code=413, detail="Payload too large")


def refuse(detail: str) -> NoReturn:
    raise HTTPException(status_code=400, detail=detail)


@router.post("/ingest/calls")
async def ingestCall(request: Request):
    if not authorizeIngest(request):
        raise HTTPException(status_code=401, detail="Invalid ingest token")

    # Refused before a byte is read when the length is declared; capped during
    # the read anyway, since Content-Length can lie.
    # The refusal is logged here: the gateway does not keep the push, so this
    # line is the only trace of a call lost for its size.
    declared = request.headers.get("Content-Length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        tooLarge(request, int(declared))
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_BODY_BYTES:
            tooLarge(request, len(body))
    # PostgreSQL stores no NUL character, in text or in jsonb: the whole call
    # would be refused by the database, and answered 503 as if it were down.
    if b"\\u0000" in body:
        refuse("the body holds a NUL character (\\u0000)")
    try:
        payload = json.loads(bytes(body))
    except (ValueError, RecursionError):        # RecursionError: nesting deeper than Python goes
        refuse("Body is not valid JSON")

    try:
        call = callRow(payload)
        media = mediaRows((payload.get("call") or {}).get("mediaStats"))
    except ValueError as exc:
        refuse(str(exc))
    except (TypeError, AttributeError, RecursionError) as exc:
        # A shape the mapping does not expect: the sender's fault, said as
        # such (400), not a server error. Logged, since the push is lost.
        log.warning("push refused, unexpected payload shape: %s", exc)
        refuse("the payload does not have the expected shape")
    # No Call-ID: a gateway container stopping without having carried a call
    # (a service restart pushes one per container). Nothing to correlate,
    # nothing to count. A Call-ID without a start is kept: a call that never
    # came up is a failure the Manager must count (outcome not_established).
    if not call["call_id"]:
        log.info("push without callId refused (a container stopped with no call)")
        raise HTTPException(status_code=400, detail="callId is missing")

    values = [call[name] for name in CALL_COLUMNS]
    values.append(Jsonb(call["media_direction"]) if call["media_direction"] is not None else None)
    values.append(Jsonb(call["dtmf_events"]))
    values.append(Jsonb(payload))

    def store():
        # One transaction: a call and its media rows are stored together or
        # not at all, never a call with half its statistics.
        with connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(INSERT_CALL, values)
                row = cursor.fetchone()
                if row is None:
                    return None            # replay guard: already stored
                for entry in media:
                    cursor.execute(INSERT_MEDIA, {"call_pk": row[0], **entry})
                return row[0]

    callPk = await run_in_threadpool(store)
    if callPk is None:
        log.info("duplicate push ignored for call %s", call["call_id"])
        return {"status": "duplicate", "stored": False}
    log.info("stored call %s as %s with %d media rows", call["call_id"], callPk, len(media))
    return {"status": "success", "stored": True,
            "call_pk": callPk, "media_rows": len(media)}
