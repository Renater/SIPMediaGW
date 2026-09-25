"""
Capacity reads one period: the routes call <view>_between(since, until), which
filters samples before aggregating. Aggregating the whole history first took
3.9 s for one month once a year of samples was stored, and grew every month
(checked against a real database in test_pool_views_db.py).
"""

import pytest

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
