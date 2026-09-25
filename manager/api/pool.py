"""
The pool: what was provisioned, what served, hour by hour.

Everything here reads pool_samples. What costs is the VM — a gateway
reporting `free` is a VM that exists with its container stopped — so
provisioned = free + idle + ivr + in_call and utilisation is measured
against it.
"""



from fastapi import APIRouter, Depends, HTTPException, Query

from api.periods import resolvePeriod, window
from auth import requireUser
from db import fetch

router = APIRouter(dependencies=[Depends(requireUser)])

# The seven weekdays, and the groups the scaler is configured in: 'default'
# is Monday to Friday; Saturday and Sunday are their own group and their own
# day, so they appear once. The front offers exactly this list.
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
DAY_TYPES = ("default",) + WEEKDAYS


@router.get("/reporting/concurrency/hourly")
def concurrencyHourly(period: str = Query(None), dayType: str = Query("default")):
    """
    Concurrency by hour, for one day type — the shape the scaler is configured in.

    Percentiles are computed per slot and not over the period: taken over a whole
    month they are dragged down by nights and weekends, and sizing on them would
    under-provision the busy hours.
    """
    if dayType not in DAY_TYPES:
        raise HTTPException(status_code=400, detail=f"dayType must be one of {', '.join(DAY_TYPES)}")
    since, until, label = resolvePeriod(period)
    rows = fetch("""
        SELECT hour, median, p90, p95, p99, peak, avg_concurrent, samples, days
          FROM hourly_concurrency_between(%s, %s)
         WHERE day_type = %s
         ORDER BY hour
    """, (since, until, dayType))
    return {"label": label, "day_type": dayType, "hours": rows}


@router.get("/reporting/pool-profile")
def poolProfile(period: str = Query(None)):
    """
    Gateway occupancy by hour and day type, for the period.

    The profile is read per period rather than over the whole history: averaged
    across a year it flattens, and what justifies changing the floor for a slot
    is precisely how that slot moved between two months.
    """
    since, until, label = resolvePeriod(period)
    rows = fetch("""
        SELECT day_type, hour, provisioned_avg, provisioned_peak, busy_avg, busy_peak,
               busy_p95, spare_avg, spare_peak, running_avg, free_avg,
               utilisation_pct, samples, days
          FROM pool_profile_between(%s, %s)
         ORDER BY day_type, hour
    """, (since, until))
    return {"label": label, "profile": rows}


@router.get("/reporting/pool-hours")
def poolHours(months: int = Query(12, ge=1, le=60)):
    """
    VM-hours per month by state, with the share of the month sampled.

    provisioned_hours is the billable total, free included: what costs is the VM,
    not the container running on it. running_hours counts warm containers only
    and is a readiness figure.

    coverage_pct matters: a Manager that was down does not produce samples, and
    the hours it missed are simply absent. A month at 80 % coverage is not a
    month with fewer gateway hours.
    """
    return fetch("""
        SELECT month::date AS month, free_hours, idle_hours, ivr_hours, call_hours,
               provisioned_hours, running_hours, utilisation_pct,
               provisioned_peak, busy_peak, samples, coverage_pct
          FROM monthly_pool_hours WHERE month >= %s ORDER BY month
    """, (window(months),))


@router.get("/reporting/pool-period-hours")
def poolPeriodHours(period: str = Query(None)):
    """
    VM-hours over the period, and the part of them spent in a conference.

    Replaces the cost of the period: a VM-hour price left out the fixed cost
    of the infrastructure and the services around it, and a figure in euros
    was read as the cost of the service. Hours are what the Manager measures;
    whoever holds the full cost model multiplies.

    coverage_pct is the share of the period elapsed so far that was sampled:
    hours missed while the Manager was down are simply absent.
    """
    since, until, label = resolvePeriod(period)
    rows = fetch("""
        SELECT ROUND(COALESCE(SUM((free + idle + ivr + in_call) * interval_s), 0) / 3600.0, 1)
                   AS provisioned_hours,
               ROUND(COALESCE(SUM(in_call * interval_s), 0) / 3600.0, 1) AS call_hours,
               ROUND(100.0 * COALESCE(SUM(interval_s), 0)
                     / NULLIF(GREATEST(EXTRACT(epoch FROM (LEAST(%s::timestamptz, now()) - %s::timestamptz)), 0), 0), 1)
                   AS coverage_pct
          FROM pool_samples WHERE ts >= %s AND ts < %s
    """, (until, since, since, until))
    result = rows[0] if rows else {"provisioned_hours": 0, "call_hours": 0, "coverage_pct": None}
    return {"label": label, **result}


@router.get("/reporting/pool-pressure")
def poolPressure(period: str = Query(None)):
    """
    Time spent with nothing left to take a new call while calls were running.

    Two degrees: no_spare covers no warm container and no provisioned VM, so a
    caller waits for a VM to be created; cold_start covers a free VM but nothing
    warm, where a call is taken in the time a container starts.

    Neither is a refusal — the scaler may well have kept up — but both say a slot
    ran without margin, which is what justifies raising its floor. Slots are
    named by their precise day: a tight Monday 9h is a Monday setting.
    """
    since, until, label = resolvePeriod(period)
    rows = fetch("""
        SELECT day_type, hour, samples, no_spare_samples, no_spare_pct,
               no_spare_minutes, cold_start_minutes
          FROM pool_pressure_between(%s, %s)
         WHERE day_type <> 'default'
         ORDER BY no_spare_minutes DESC
    """, (since, until))
    return {"label": label, "slots": rows}
