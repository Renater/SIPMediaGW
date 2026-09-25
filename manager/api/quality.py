"""
Quality of service: what completed, what did not, and why.
"""

from fastapi import APIRouter, Depends, Query

from api.periods import callScope, resolvePeriod
from auth import requireUser
from db import fetch, sqlWith

router = APIRouter(dependencies=[Depends(requireUser)])

@router.get("/reporting/ivr-reasons")
def ivrReasons(period: str = Query(None), limit: int = Query(30, ge=1, le=200)):
    """
    Every close reason over the period, with what it produced and whether it
    counts as a failure.

    Listing only the unclassified ones answered a maintainer's question. A reader
    wants the other one: what ends a call here, and is that normal. A reason that
    ends completed calls is normal however alarming it reads — the conference had
    been joined before it fired.

    The ones that are neither failures nor completions are the candidates for
    is_technical_failure(); recompute_outcomes() replays the history once one is
    added.
    """
    since, until, _ = resolvePeriod(period)
    return fetch("""
        SELECT COALESCE(NULLIF(close_reason, ''), '(aucune cause)') AS close_reason,
               outcome,
               is_technical_failure(close_reason) AS is_failure,
               COUNT(*) AS sessions,
               ROUND(100.0 * COUNT(*) / NULLIF(SUM(COUNT(*)) OVER (), 0), 1) AS pct,
               ROUND(AVG(occupancy_s)) AS avg_occupancy_s
          FROM calls
         WHERE is_user_call(main_app) AND call_start >= %s AND call_start < %s
         GROUP BY 1, 2, 3 ORDER BY sessions DESC LIMIT %s
    """, (since, until, limit))


@router.get("/reporting/recomputes")
def recomputes(limit: int = Query(20, ge=1, le=100)):
    """
    History of recomputations, so a gap between a published slide and the tool
    can be explained rather than suspected.
    """
    return fetch("""
        SELECT ran_at, target, rows_seen, rows_moved, ran_by, note
          FROM recompute_log ORDER BY ran_at DESC LIMIT %s
    """, (limit,))


@router.get("/reporting/outcomes")
def outcomes(period: str = Query(None), units: str = Query(None)):
    """Sessions per outcome over the period: what the service did not deliver."""
    since, until, label = resolvePeriod(period)
    where, unitParams = callScope(units)
    rows = fetch(sqlWith("""
        SELECT outcome, COUNT(*) AS sessions,
               ROUND(SUM(occupancy_s) / 3600.0, 1) AS gateway_hours
          FROM calls WHERE call_start >= %s AND call_start < %s{where}
         GROUP BY outcome ORDER BY sessions DESC
    """, where=where), [since, until] + unitParams)
    # The window travels with the counts: a row of the Quality view opens the
    # Journal on exactly these calls.
    return {"label": label, "since": since.isoformat(), "until": until.isoformat(),
            "outcomes": rows}


@router.get("/reporting/video-states")
def videoStates(period: str = Query(None), units: str = Query(None)):
    """
    Conferences joined over the period, by what the samples said of the
    picture received (SIPMediaGW #101). NULL is "not measured": calls before
    the samples existed, or too short for two of them.
    """
    since, until, label = resolvePeriod(period)
    where, unitParams = callScope(units)
    rows = fetch(sqlWith("""
        SELECT COALESCE(video_state, 'unknown') AS video_state, COUNT(*) AS sessions
          FROM calls
         WHERE outcome = 'completed' AND call_start >= %s AND call_start < %s{where}
         GROUP BY 1 ORDER BY sessions DESC
    """, where=where), [since, until] + unitParams)
    return {"label": label, "since": since.isoformat(), "until": until.isoformat(),
            "states": rows}
