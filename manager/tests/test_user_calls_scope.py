"""
P27, from the review of 24/09: Usage and Quality count user calls only, all
of them — the tiles counted recording and streaming sessions while the monthly
chart and the close reasons did not — and the peak follows the units ticked.
"""

import pytest

from api.periods import USER_CALLS, callScope
from tests.test_api_routes import SAMPLE_ROW

SCOPED = ["/api/reporting/summary", "/api/reporting/platforms", "/api/reporting/org-units",
          "/api/reporting/outcomes", "/api/reporting/video-states"]


def test_the_scope_is_user_calls_then_units():
    assert callScope(None) == (USER_CALLS, [])
    where, params = callScope("SALES,(unassigned)")
    assert where.startswith(" AND is_user_call(main_app) AND (")
    assert params == [["SALES"]]


@pytest.mark.parametrize("path", SCOPED)
def test_every_usage_and_quality_count_keeps_to_user_calls(client, path):
    client.recorder.rows = [SAMPLE_ROW]     # an aggregate always answers one row
    assert client.get(path, params={"period": "2026-09", "units": "SALES"}).status_code == 200
    counted = [q for q, _ in client.recorder.calls if "FROM calls" in q]
    assert counted, path
    for query in counted:
        assert "is_user_call(main_app)" in query, f"{path}: {query[:120]}"


def test_the_peak_follows_the_units_and_reads_the_period_only(client):
    client.recorder.rows = [SAMPLE_ROW]
    client.get("/api/reporting/summary", params={"period": "2026-09", "units": "SALES"})
    peak = client.recorder.queriesMentioning("UNBOUNDED PRECEDING")
    assert peak, "the peak is no longer swept over the period"
    query, params = next((q, p) for q, p in client.recorder.calls if q == peak[-1])
    assert "daily_peak_concurrency" not in query, "the whole-table view knows nothing of units"
    assert "call_end > %s AND call_start < %s" in query
    assert params.count(["SALES"]) == 2, "both halves of the sweep carry the units"


def test_a_journal_filter_keeps_to_the_calls_quality_counted(client):
    client.get("/api/reporting/calls", params={"outcome": "completed"})
    assert "is_user_call(main_app)" in client.recorder.calls[-1][0]
    client.get("/api/reporting/calls", params={"video": "stalled"})
    assert "is_user_call(main_app)" in client.recorder.calls[-1][0]
    # Without a filter, the Journal lists every session, recordings included.
    client.get("/api/reporting/calls")
    assert "is_user_call" not in client.recorder.calls[-1][0]
