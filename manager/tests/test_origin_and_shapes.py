"""
P26, from the review of 24/09, the parts that need no web framework: which
writes origin.py refuses, and how the mapping reads a push of the wrong shape.
The routes are played in test_writes_and_sessions.py.
"""

import pytest

import origin
from ingest.mapping import _float, _int, callRow, mediaRows

HOST = "192.0.2.10:8200"


# ------------------------------------------------------------ origin.py (no FastAPI needed)

@pytest.mark.parametrize("method", ["GET", "HEAD", "OPTIONS"])
def test_reads_are_never_checked(method):
    assert origin.refusal(method, "/api/users", {"origin": "https://evil.example", "host": HOST}) is None


def test_a_same_origin_write_passes():
    headers = {"origin": f"http://{HOST}", "host": HOST, "sec-fetch-site": "same-origin"}
    assert origin.refusal("POST", "/api/org-units/recompute", headers) is None


def test_no_browser_no_check():
    """curl, the tests, a script: no cookie lent by anyone, nothing to forge."""
    assert origin.refusal("POST", "/api/users", {"host": HOST}) is None


@pytest.mark.parametrize("headers", [
    # interact on :80 of the same host: same site, another origin — the case SameSite lets through
    {"origin": "http://192.0.2.10", "host": HOST, "sec-fetch-site": "same-site"},
    {"origin": "http://192.0.2.10", "host": HOST},
    {"origin": "https://troubleshoot.sample.org", "host": "manager.sample.org"},
    {"host": HOST, "sec-fetch-site": "cross-site"},
    {"origin": "null", "host": HOST},
])
def test_another_origin_is_refused(headers):
    assert origin.refusal("POST", "/api/org-units/recompute", headers)


def test_the_forwarded_host_counts_only_behind_a_proxy():
    headers = {"origin": "https://manager.example", "host": "192.0.2.10:8200",
               "x-forwarded-host": "manager.example"}
    assert origin.refusal("PUT", "/api/users/x", headers, trustForwardedHost=True) is None
    assert origin.refusal("PUT", "/api/users/x", headers, trustForwardedHost=False)


def test_ingest_is_left_to_its_token():
    assert origin.refusal("POST", "/ingest/calls", {"origin": "https://evil.example", "host": HOST}) is None


# ------------------------------------------------------------ mapping (no FastAPI needed)

@pytest.mark.parametrize("value", [1e20, float("inf"), float("-inf"), "99999999999", 2**31])
def test_a_number_no_column_holds_is_read_as_missing(value):
    assert _int(value) is None


def test_a_number_that_is_not_one_is_read_as_missing():
    assert _float(float("nan")) is None and _float(float("inf")) is None
    assert _int(42.0) == 42 and _float("3.5") == 3.5


@pytest.mark.parametrize("call", [
    {"callSession": "x", "details": {"callId": "a"}},
    {"callSession": {"totalTime": [1]}, "details": {"callId": "a", "source": "x", "destination": 3}},
    {"details": [], "callSession": {"callStart": "x", "callEnd": 5}},
])
def test_a_block_of_the_wrong_kind_is_read_as_absent(call):
    row = callRow({"call": call})
    assert row["duration_s"] is None or isinstance(row["duration_s"], int)


@pytest.mark.parametrize("stats", [[], "x", {"audio": [1], "video": "x"}, {"audio": {"tx": [1]}}])
def test_media_of_the_wrong_kind_gives_no_row(stats):
    assert mediaRows(stats) == []
