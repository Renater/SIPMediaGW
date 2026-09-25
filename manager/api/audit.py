"""
The administration audit, in one list: accounts and entities.

Each side keeps its own table, written in the same statement as the change
it records (user_audit by users.py, org_unit_audit by the entity routes).
They are read together here, each line carrying its type, over a window of
dates, searchable by person, a page at a time.
"""

import datetime as dt
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from api.periods import aware, parseInstant
from auth import requireAdmin
from db import fetch, likePattern

router = APIRouter()

TYPES = ("user", "entity")


@router.get("/audit")
def readAudit(types: str = Query("user,entity", max_length=40),
              start: str = Query(None), end: str = Query(None),
              q: str = Query("", max_length=120),
              limit: int = Query(50, ge=1, le=500),
              offset: int = Query(0, ge=0),
              user: str = Depends(requireAdmin)):
    """
    Newest first. types: user, entity or both. q searches who acted and on
    whom: "toto" finds what toto did and what was done to toto's account.
    Without dates, the last 30 days.
    """
    wanted = [value for value in types.split(",") if value]
    if not wanted or any(value not in TYPES for value in wanted):
        raise HTTPException(status_code=400, detail="types must be user, entity or both")
    until = parseInstant(end) or aware(dt.datetime.combine(date.today(), dt.time.max))
    since = parseInstant(start) or aware(dt.datetime.combine(date.today() - dt.timedelta(days=29), dt.time.min))
    if until < since:
        raise HTTPException(status_code=400, detail="end is before start")
    pattern = likePattern(q.strip())
    rows = fetch("""
        WITH lines AS (
            SELECT 'user' AS type, id, at, actor, action, target, detail FROM user_audit WHERE %s
            UNION ALL
            SELECT 'entity' AS type, id, at, actor, action, target, detail FROM org_unit_audit WHERE %s
        )
        SELECT type, at, actor, action, target, detail, COUNT(*) OVER () AS total
          FROM lines
         WHERE at >= %s AND at <= %s
           AND (%s = '' OR actor ILIKE %s OR target ILIKE %s)
         ORDER BY at DESC, id DESC
         LIMIT %s OFFSET %s
    """, ("user" in wanted, "entity" in wanted, since, until,
          q.strip(), pattern, pattern, limit, offset))
    total = rows[0]["total"] if rows else 0
    lines = [{key: value for key, value in row.items() if key != "total"} for row in rows]
    return {"total": total, "limit": limit, "offset": offset,
            "start": since.isoformat(), "end": until.isoformat(), "lines": lines}
