"""
The call log: search, one call's detail, its media statistics.
"""

import datetime as dt
import json
import re
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from api.periods import aware, parseInstant
from auth import requireUser
from db import fetch, likePattern, sqlWith
from homer import callLink
from ingest.mapping import frameRates

router = APIRouter(dependencies=[Depends(requireUser)])

OUTCOMES = ("not_established", "completed", "failed", "ivr_only")
VIDEO_STATES = ("ok", "oneway", "stalled", "no_picture", "unknown")
NO_REASON = "(aucune cause)"      # how the Quality view names an empty close reason

# What the search box looks into. The Call-ID stays: support often starts from
# one seen in Homer. Fixed column names, no value: the clause is built once.
SEARCHED = ("call_id", "room", "source_uri", "source_number", "source_name",
            "peer_display_name", "gw_alias", "org_unit", "peer_user_agent",
            "gw_version", "baresip_patch", "video_codec", "audio_codec")
SEARCH_CLAUSE = " OR ".join(f"{column} ILIKE %s" for column in SEARCHED)


def terminalLabel(userAgent):
    """
    The endpoint's model, short enough for a column. Cisco puts it after the
    firmware: 'TANDBERG/529 (ce11.40.1.1.10bdaa53ce2) Cisco-RoomKitMini'
    -> 'Cisco-RoomKitMini'. Otherwise the product token: 'Linphone/5.2.0
    (belle-sip/5.2.0)' -> 'Linphone/5.2.0'. The full string is in the drawer.
    """
    text = (userAgent or "").strip()
    if not text:
        return None
    after = text.rsplit(")", 1)[1].strip() if ")" in text else ""
    return after or text.split()[0]


def choices(value: str | None, allowed, what: str) -> list[str]:
    """
    One value or several, comma-separated: the Journal's lists tick any number
    of them. Every value must be known, or the answer would silently narrow to
    the known ones.
    """
    picked = [item for item in (value or "").split(",") if item]
    if any(item not in allowed for item in picked):
        raise HTTPException(status_code=400, detail=f"unknown {what}")
    return picked


def callWindow(start: str | None, end: str | None):
    """The explicit window; today by default."""
    since = parseInstant(start) or aware(dt.datetime.combine(date.today(), dt.time.min))
    until = parseInstant(end) or aware(dt.datetime.combine(date.today(), dt.time.max))
    if until < since:
        raise HTTPException(status_code=400, detail="end is before start")
    return since, until


def exactFilters(reason: str | None, outcomes: list[str], videos: list[str]):
    """
    The exact filters, as fixed SQL fragments and their parameters.

    Any of them keeps to user calls, as the Quality counts do (is_user_call):
    a Quality row opens the Journal on the same calls it counted, recordings
    and streams left out. Without a filter the Journal lists every session.
    """
    filters: list[str] = []
    params: list = []
    if reason is not None:
        filters.append("COALESCE(NULLIF(close_reason, ''), %s) = %s")
        params += [NO_REASON, reason]
    if outcomes:
        filters.append("outcome = ANY(%s)")
        params.append(outcomes)
    if videos:
        # "unknown" is NULL in the table, which ANY() never matches.
        known = [value for value in videos if value != "unknown"]
        clauses = (["video_state = ANY(%s)"] if known else []) + (
            ["video_state IS NULL"] if "unknown" in videos else [])
        filters.append("(" + " OR ".join(clauses) + ")")
        if known:
            params.append(known)
    if filters:
        filters.insert(0, "is_user_call(main_app)")
    return "".join(" AND " + clause for clause in filters), params


def listed(rows):
    """What the list shows of a call: the terminal's short name, not the User-Agent."""
    for row in rows:
        row.pop("total", None)
        row["terminal"] = terminalLabel(row.pop("peer_user_agent", None))
    return rows


@router.get("/reporting/calls")
def searchCalls(start: str = Query(None), end: str = Query(None),
                q: str = Query("", max_length=120),
                reason: str = Query(None, max_length=300),
                outcome: str = Query(None, max_length=120),
                video: str = Query(None, max_length=120),
                limit: int = Query(50, ge=1, le=500),
                offset: int = Query(0, ge=0)):
    """
    Call log over an explicit window, searchable and paginated.

    A day can hold several hundred calls, so the window carries a time of day
    and the result is a page plus the total, not the whole history.

    reason, outcome and video are exact filters, for the links of the Quality
    view: a close reason searched as text would also bring back every normal
    call ending on the same reason.
    """
    outcomes = choices(outcome, OUTCOMES, "outcome")
    videos = choices(video, VIDEO_STATES, "video state")
    since, until = callWindow(start, end)
    window = {"start": since.isoformat(), "end": until.isoformat()}

    # "#3197": the call number shown in the drawer. It names one call, so the
    # window does not apply — whoever has the number rarely has the date.
    number = re.fullmatch(r"#(\d{1,18})", q.strip())
    if number:
        rows = listed(fetch("""
            SELECT id, call_id, call_start, call_end, duration_s, occupancy_s, outcome,
                   platform, room, source_uri, source_name, source_number, source_domain,
                   peer_display_name, gw_alias, org_unit, close_reason,
                   peer_user_agent, video_state
              FROM calls WHERE id = %s
        """, (int(number.group(1)),)))
        return {"total": len(rows), "limit": limit, "offset": 0, **window, "calls": rows}

    pattern = likePattern(q)
    filters, params = exactFilters(reason, outcomes, videos)
    rows = fetch(sqlWith("""
        SELECT id, call_id, call_start, call_end, duration_s, occupancy_s, outcome,
               platform, room, source_uri, source_name, source_number, source_domain,
               peer_display_name, gw_alias, org_unit, close_reason,
               peer_user_agent, video_state,
               COUNT(*) OVER () AS total
          FROM calls
         WHERE call_start >= %s AND call_start <= %s
           AND (%s = '' OR {search}){filters}
         ORDER BY call_start DESC NULLS LAST
         LIMIT %s OFFSET %s
    """, search=SEARCH_CLAUSE, filters=filters), [since, until, q] + [pattern] * len(SEARCHED) + params + [limit, offset])
    total = rows[0]["total"] if rows else 0
    return {"total": total, "limit": limit, "offset": offset, **window, "calls": listed(rows)}


@router.get("/reporting/calls/{callPk}")
def callDetail(callPk: int):
    """Everything the gateway pushed for one call, media statistics included."""
    rows = fetch("""
        SELECT id, received_at, call_id, gw_alias, gw_id, gw_host, main_app, platform,
               room, call_url, source_uri, source_name, source_number, source_domain,
               destination_uri, destination_room, destination_domain, peer_display_name,
               call_start, call_end, duration_s, occupancy_s, outcome, close_reason,
               last_event_type, org_unit, dtmf_events, raw,
               established, peer_user_agent, audio_codec, video_codec, video_encoder,
               media_direction, gw_version, baresip_version, baresip_patch, chromium_version,
               video_state, video_min_rx_fps, video_low_intervals, video_keyframe_requests,
               presentation_s
          FROM calls WHERE id = %s
    """, (callPk,))
    if not rows:
        raise HTTPException(status_code=404, detail="Call not found")
    call = rows[0]
    # Built server-side: base URL, flavor and retention live in the config, and
    # a None here is what makes the front show no link at all. The kind tells
    # the front how to label it: an exact Call-ID match, or a room search that
    # may return several calls.
    call["homer_url"], call["homer_link_kind"] = callLink(call)
    call["terminal"] = terminalLabel(call.get("peer_user_agent"))
    # Frames per second over the call, for the drawer's chart: computed from
    # the samples kept in raw, not stored twice.
    stats = ((call.get("raw") or {}).get("call") or {}).get("mediaStats") or {}
    call["frame_rates"] = frameRates(stats.get("samples") if isinstance(stats, dict) else None)
    call["media"] = fetch("""
        SELECT media, stream_index, direction, packets, lost_packets, jitter_ms,
               avg_bitrate_kbps, errors, packet_reports
          FROM call_media_stats WHERE call_pk = %s
         ORDER BY media, stream_index, direction
    """, (callPk,))
    return call


@router.get("/reporting/calls/{callPk}/raw")
def callRaw(callPk: int):
    """
    The payload exactly as the gateway pushed it, as a file: what support
    attaches to a ticket or hands to whoever maintains the gateway. Same
    access as the drawer, which already shows it.
    """
    rows = fetch("SELECT id, call_id, call_start, raw FROM calls WHERE id = %s", (callPk,))
    if not rows:
        raise HTTPException(status_code=404, detail="Call not found")
    call = rows[0]
    start = call["call_start"]
    stamp = start.strftime("%Y%m%d-%H%M%S") if hasattr(start, "strftime") else "undated"
    # The Call-ID goes into a header: only characters that cannot break it.
    callId = re.sub(r"[^A-Za-z0-9._-]", "_", call["call_id"] or "")[:64]
    name = "-".join(part for part in ("call", str(call["id"]), stamp, callId) if part) + ".json"
    return Response(content=json.dumps(call["raw"], ensure_ascii=False, indent=2),
                    media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
