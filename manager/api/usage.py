"""
Usage and adoption: how much the service is used, by whom, on what.
"""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query

from api.periods import callScope, resolvePeriod, window
from auth import requireUser
from db import fetch, sqlWith

router = APIRouter(dependencies=[Depends(requireUser)])

@router.get("/reporting/summary")
def summary(period: str = Query(None), units: str = Query(None)):
    """Headline figures for the period, service and consumption side by side."""
    since, until, label = resolvePeriod(period)
    where, unitParams = callScope(units)
    rows = fetch(sqlWith("""
        SELECT COUNT(*) FILTER (WHERE outcome = 'completed')            AS calls,
               ROUND(COALESCE(SUM(duration_s) FILTER (WHERE outcome = 'completed'), 0) / 3600.0, 1) AS hours,
               COALESCE(SUM(duration_s) FILTER (WHERE outcome = 'completed'), 0) AS seconds,
               COUNT(*)                                                 AS sessions,
               ROUND(COALESCE(SUM(occupancy_s), 0) / 3600.0, 1)         AS gateway_hours,
               COUNT(*) FILTER (WHERE outcome = 'failed')               AS failed,
               COUNT(*) FILTER (WHERE outcome = 'ivr_only')             AS ivr_only,
               COUNT(*) FILTER (WHERE outcome = 'not_established')      AS not_established,
               COUNT(DISTINCT source_number)                            AS endpoints
          FROM calls WHERE call_start >= %s AND call_start < %s{where}
    """, where=where), [since, until] + unitParams)
    # The most calls at once during the period, over the same calls as the
    # other tiles (units included). Swept over the calls that overlap the
    # period only: daily_peak_concurrency sorted the whole table on every
    # request, and knew nothing of units. A call begun before the period
    # counts from its start, so the running total is right at `since`.
    overlap = sqlWith("""established AND call_start IS NOT NULL AND call_end IS NOT NULL
                  AND call_end > %s AND call_start < %s{where}""", where=where)
    peak = fetch(sqlWith("""
        WITH ev AS (
            SELECT call_start AS t, 1 AS d FROM calls WHERE {overlap}
            UNION ALL
            SELECT call_end AS t, -1 AS d FROM calls WHERE {overlap}
        )
        SELECT COALESCE(MAX(running), 0) AS peak
          FROM (SELECT SUM(d) OVER (ORDER BY t, d ROWS UNBOUNDED PRECEDING) AS running FROM ev) sweep
    """, overlap=overlap), [since, until] + unitParams + [since, until] + unitParams)
    result = rows[0]
    result["peak_concurrent"] = peak[0]["peak"]
    result["label"] = label
    result["since"] = since.isoformat()
    result["until"] = until.isoformat()
    return result


@router.get("/reporting/monthly")
def monthly(months: int = Query(18, ge=1, le=60)):
    """
    Monthly series with a running total and a least-squares trend, which is
    what the cumulative histogram draws.
    """
    rows = fetch("""
        SELECT month::date AS month, calls, hours, avg_seconds
          FROM monthly_service WHERE month >= %s ORDER BY month
    """, (window(months),))

    cumulativeCalls = 0
    cumulativeHours = 0.0
    for row in rows:
        cumulativeCalls += row["calls"] or 0
        cumulativeHours += float(row["hours"] or 0)
        row["cumulative_calls"] = cumulativeCalls
        row["cumulative_hours"] = round(cumulativeHours, 1)

    # Least-squares fit on hours, so the report can show the direction of
    # travel rather than leaving the reader to eyeball it.
    trend = []
    n = len(rows)
    if n >= 2:
        xs = list(range(n))
        ys = [float(r["hours"] or 0) for r in rows]
        meanX = sum(xs) / n
        meanY = sum(ys) / n
        denominator = sum((x - meanX) ** 2 for x in xs)
        slope = (sum((x - meanX) * (y - meanY) for x, y in zip(xs, ys)) / denominator
                 if denominator else 0.0)
        intercept = meanY - slope * meanX
        trend = [round(intercept + slope * x, 1) for x in xs]

    return {"months": rows, "trend_hours": trend}


@router.get("/reporting/platforms")
def platforms(period: str = Query(None), units: str = Query(None)):
    since, until, _ = resolvePeriod(period)
    where, unitParams = callScope(units)
    # Read from calls, not the monthly view: a period can be a day or a week.
    return fetch(sqlWith("""
        SELECT COALESCE(platform, '(none)') AS platform, COUNT(*) AS calls,
               ROUND(SUM(duration_s) / 3600.0, 1) AS hours
          FROM calls
         WHERE outcome = 'completed' AND call_start >= %s AND call_start < %s{where}
         GROUP BY 1 ORDER BY calls DESC
    """, where=where), [since, until] + unitParams)


@router.get("/reporting/org-units")
def orgUnits(period: str = Query(None), units: str = Query(None)):
    """Share of calls per organisational unit, and each unit's platform mix."""
    since, until, label = resolvePeriod(period)
    where, unitParams = callScope(units)
    rows = fetch(sqlWith("""
        SELECT COALESCE(org_unit, '(unassigned)') AS org_unit, COUNT(*) AS calls,
               ROUND(SUM(duration_s) / 3600.0, 1) AS hours
          FROM calls
         WHERE outcome = 'completed' AND call_start >= %s AND call_start < %s{where}
         GROUP BY 1 ORDER BY calls DESC
    """, where=where), [since, until] + unitParams)
    total = sum(row["calls"] for row in rows) or 1
    for row in rows:
        row["pct"] = round(100.0 * row["calls"] / total, 1)
    mix = fetch(sqlWith("""
        SELECT COALESCE(org_unit, '(unassigned)') AS org_unit,
               COALESCE(platform, '(none)') AS platform, COUNT(*) AS calls
          FROM calls
         WHERE outcome = 'completed' AND call_start >= %s AND call_start < %s{where}
         GROUP BY 1, 2 ORDER BY 1, calls DESC
    """, where=where), [since, until] + unitParams)
    return {"label": label, "units": rows, "platform_mix": mix}


@router.get("/reporting/concurrency")
def concurrency(days: int = Query(31, ge=1, le=366)):
    return fetch("""
        SELECT day, peak_concurrent FROM daily_peak_concurrency
         WHERE day >= %s ORDER BY day
    """, (date.today() - timedelta(days=days),))
