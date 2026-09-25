"""
Periods, windows and the unit filter — what every reporting route agrees on.

A period name or a month resolves to one half-open interval here, and one
place decides that `today` ends at local midnight. The unit filter is here
too, because every route that takes `units` must read it the same way.
"""

import re
import datetime as dt
from datetime import date, timedelta

from fastapi import HTTPException

def aware(value):
    """
    A datetime that can be compared with any other one.

    Naive means local: that is what the proxy writes into call_started and
    what an operator types into a date filter. Attached here, once, so that
    no comparison downstream can raise "can't compare offset-naive and
    offset-aware datetimes" — which took the park view down as soon as Homer
    retention was configured.
    """
    if value is None or value.tzinfo is not None:
        return value
    return value.astimezone()


def parseInstant(value):
    """Accept an ISO 8601 instant, with or without a time of day or a zone."""
    if not value:
        return None
    try:
        return aware(dt.datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        raise HTTPException(status_code=400, detail=f"invalid datetime: {value}")


def window(months: int):
    """Start of the period: `months` whole months back from this month."""
    first = date.today().replace(day=1)
    for _ in range(months - 1):
        first = (first - timedelta(days=1)).replace(day=1)
    return first


def previousMonth(today: date | None = None):
    """First day of the month that has just ended."""
    today = today or date.today()
    return (today.replace(day=1) - timedelta(days=1)).replace(day=1)


def nextMonth(first: date):
    return (first.replace(day=28) + timedelta(days=7)).replace(day=1)


def checkedYear(year: int) -> int:
    """
    A year the reports can mean. Outside this range date() itself fails
    (year 0, or year + 1 past 9999) and the error answered 500.
    """
    if not 1970 <= year <= 2100:
        raise HTTPException(status_code=400, detail="year out of range (1970-2100)")
    return year


# Named periods an operator actually asks for. Weeks start on Monday.


PERIODS = ("today", "week", "last_week", "month", "last_month", "year", "last_year")


def resolvePeriod(period: str | None, today: date | None = None):
    """
    Resolve a reporting period to [since, until) plus a label.

    Accepts a named period, "YYYY-MM" for a single month, or "YYYY" for a year.
    Defaults to the month that has just ended: that is what the monthly report
    is about.
    """
    today = today or date.today()
    if not period or period == "last_month":
        first = previousMonth(today)
        return first, nextMonth(first), first.isoformat()[:7]
    if period == "today":
        return today, today + timedelta(days=1), today.isoformat()
    if period == "week":
        first = today - timedelta(days=today.weekday())
        return first, first + timedelta(days=7), f"week of {first.isoformat()}"
    if period == "last_week":
        first = today - timedelta(days=today.weekday() + 7)
        return first, first + timedelta(days=7), f"week of {first.isoformat()}"
    if period == "month":
        first = today.replace(day=1)
        return first, nextMonth(first), first.isoformat()[:7]
    if period == "year":
        return date(today.year, 1, 1), date(today.year + 1, 1, 1), str(today.year)
    if period == "last_year":
        return date(today.year - 1, 1, 1), date(today.year, 1, 1), str(today.year - 1)
    if re.fullmatch(r"\d{4}", period or ""):
        year = checkedYear(int(period))
        return date(year, 1, 1), date(year + 1, 1, 1), period
    if re.fullmatch(r"\d{4}-\d{2}", period or ""):
        year, month = (int(part) for part in period.split("-"))
        if not 1 <= month <= 12:
            raise HTTPException(status_code=400, detail="month out of range")
        first = date(checkedYear(year), month, 1)
        return first, nextMonth(first), period
    raise HTTPException(status_code=400,
                        detail="period must be YYYY-MM, YYYY or one of " + ", ".join(PERIODS))


# Recording and streaming sessions hold a gateway but carry no caller: they
# count in Capacity (the pool) and never in Usage or Quality, which count
# what users did. is_user_call() is the one definition (schema, lot 0).
USER_CALLS = " AND is_user_call(main_app)"


def callScope(units: str | None):
    """
    The calls Usage and Quality count — user calls, of the chosen units — as
    a SQL fragment of fixed text and its parameters. Every figure of those two
    views reads through it, so the tiles, the charts and the lists count the
    same calls (the monthly chart and the close reasons already filtered user
    calls; the tiles did not).
    """
    where, params = unitFilter(units)
    return USER_CALLS + where, params


def unitFilter(units: str | None):
    """
    Turn the `units` query parameter into a SQL fragment and its parameters.

    Empty or absent means every unit, which is the default the front sends when
    all boxes are ticked: filtering on the full list and filtering on nothing
    must give the same figures, or the totals would move as boxes are ticked.

    '(unassigned)' is selectable like any other, and matches rows whose org_unit
    is NULL — otherwise the share that no rule catches would be impossible to
    look at, and it is precisely the one worth looking at.
    """
    if not units:
        return "", []
    wanted = [u.strip() for u in units.split(",") if u.strip()]
    if not wanted:
        return "", []
    named = [u for u in wanted if u != "(unassigned)"]
    clauses, params = [], []
    if named:
        clauses.append("org_unit = ANY(%s)")
        params.append(named)
    if len(named) != len(wanted):
        clauses.append("org_unit IS NULL")
    return " AND (" + " OR ".join(clauses) + ")", params
