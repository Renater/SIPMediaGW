"""
P13 — Capacity reads one period, and compares with the right one.

P-03  The day-type views aggregated the whole history before the month was
      kept: 3.9 s for one month once a year of samples was stored, growing
      every month. The routes now call <view>_between(since, until), which
      filters samples before aggregating (checked against a real database in
      test_pool_views_db.py).
B-02  "The period before" was the same number of days earlier: 2 Aug – 1 Sep
      for September, which the month filter turned into nothing. A month now
      compares with the calendar month before it.
"""

from datetime import date
from pathlib import Path

import pytest

from api.pool import previousPeriod

ROUTES = {
    "/api/reporting/pool-profile": "pool_profile_between",
    "/api/reporting/pool-pressure": "pool_pressure_between",
    "/api/reporting/concurrency/hourly": "hourly_concurrency_between",
}


@pytest.mark.parametrize("path, function", ROUTES.items())
def test_capacity_routes_filter_before_aggregating(client, path, function):
    client.get(f"{path}?period=2026-08")
    sql = " ".join(call[0] for call in client.recorder.calls)
    assert f"FROM {function}(" in sql, f"{path} reads the whole-history view"


@pytest.mark.parametrize("month, before", [
    ((2026, 9, 1), (2026, 8, 1)),     # 30 days after 31: the case that came back empty
    ((2026, 3, 1), (2026, 2, 1)),     # 31 after 28
    ((2026, 1, 1), (2025, 12, 1)),    # across the new year
    ((2024, 3, 1), (2024, 2, 1)),     # after a leap February
])
def test_a_month_compares_with_the_calendar_month_before(month, before):
    since = date(*month)
    until = date(since.year + (since.month == 12), since.month % 12 + 1, 1)
    assert previousPeriod(since, until) == (date(*before), since)


def test_other_periods_keep_the_same_length():
    assert previousPeriod(date(2026, 9, 14), date(2026, 9, 21)) == (date(2026, 9, 7), date(2026, 9, 14))


def test_the_profile_route_asks_for_the_month_before(client):
    response = client.get("/api/reporting/pool-profile?period=2026-09&compare=true")
    params = [call[1] for call in client.recorder.calls]
    assert (date(2026, 8, 1), date(2026, 9, 1)) in [tuple(p) for p in params], params
    assert response.json()["previous_label"] == "2026-08", "the chart could not name the dotted lines"


def test_period_labels():
    from api.pool import periodLabel
    assert periodLabel(date(2026, 8, 1), date(2026, 9, 1)) == "2026-08"
    assert periodLabel(date(2025, 1, 1), date(2026, 1, 1)) == "2025"
    assert periodLabel(date(2026, 9, 7), date(2026, 9, 14)) == "2026-09-07 – 2026-09-13"


def test_the_chart_scales_on_both_periods_and_names_the_previous_one():
    """
    With the comparison back, a busier August was drawn past the top of the
    September chart, with nothing saying what the faint lines were.
    """
    charts = (Path(__file__).resolve().parent.parent / "front" / "js" / "charts.js").read_text()
    body = charts[charts.index("export function hourlyLines"):charts.index("export function monthlyPairs")]
    peak = body[body.index("const peak"):body.index(";", body.index("const peak"))]
    assert "prevByHour" in peak, "the scale ignores the previous period"
    assert body.count('stroke-dasharray="5 4"') >= 2, "the previous period is not dotted in the chart and the legend"
    assert "ghostName(s)" in body[body.index("const legend"):], "the legend does not name the previous period"
