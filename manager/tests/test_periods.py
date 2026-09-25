"""resolvePeriod: every preset, the explicit forms, and the edge dates."""
from datetime import date

import pytest
from fastapi import HTTPException

from api.periods import resolvePeriod

FRIDAY = date(2026, 9, 4)


@pytest.mark.parametrize("period, since, until, label", [
    ("today",      date(2026, 9, 4),  date(2026, 9, 5),  "2026-09-04"),
    ("week",       date(2026, 8, 31), date(2026, 9, 7),  "week of 2026-08-31"),   # Monday
    ("last_week",  date(2026, 8, 24), date(2026, 8, 31), "week of 2026-08-24"),
    ("month",      date(2026, 9, 1),  date(2026, 10, 1), "2026-09"),
    ("last_month", date(2026, 8, 1),  date(2026, 9, 1),  "2026-08"),
    (None,         date(2026, 8, 1),  date(2026, 9, 1),  "2026-08"),                 # default
    ("year",       date(2026, 1, 1),  date(2027, 1, 1),  "2026"),
    ("last_year",  date(2025, 1, 1),  date(2026, 1, 1),  "2025"),
    ("2026-02",    date(2026, 2, 1),  date(2026, 3, 1),  "2026-02"),
    ("2026-12",    date(2026, 12, 1), date(2027, 1, 1),  "2026-12"),                 # year roll-over
    ("2025",       date(2025, 1, 1),  date(2026, 1, 1),  "2025"),
])
def test_presets_and_explicit_forms(period, since, until, label):
    assert resolvePeriod(period, today=FRIDAY) == (since, until, label)


def test_last_month_across_new_year():
    assert resolvePeriod("last_month", today=date(2026, 1, 15))[:2] == (date(2025, 12, 1), date(2026, 1, 1))


@pytest.mark.parametrize("bad", ["yesterday", "2026-13", "20-01", "'; DROP TABLE calls; --"])
def test_invalid_periods_are_rejected(bad):
    with pytest.raises(HTTPException) as error:
        resolvePeriod(bad, today=FRIDAY)
    assert error.value.status_code == 400


def test_parse_instant_is_always_aware():
    """
    start=…Z and a missing end once met in `until < since` as aware vs naive:
    TypeError, 500. Both sides now carry a zone, whatever the caller typed.
    """
    from api.periods import parseInstant
    withZone = parseInstant("2026-09-01T10:00:00Z")
    local = parseInstant("2026-09-01T10:00:00")
    assert withZone.tzinfo is not None and local.tzinfo is not None
    # Comparable (naive against aware raised TypeError), and apart by no more
    # than a time-zone offset, whichever zone the session runs in.
    assert abs((local - withZone).total_seconds()) <= 14 * 3600
    assert parseInstant("") is None
