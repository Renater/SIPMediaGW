"""
Homer deep links: the validated v7 shape, filter names, and when no link is offered.

The filter name is the fragile part — an unrecognised one is silently ignored
by Homer and yields every call in the window — so the tests assert the exact
key and value shape rather than just "a URL was produced".
"""
import datetime as dt
import json
from urllib.parse import unquote

import pytest

import homer

START = dt.datetime(2026, 9, 6, 8, 30, 0, tzinfo=dt.timezone.utc)
END = dt.datetime(2026, 9, 6, 8, 35, 0, tzinfo=dt.timezone.utc)
START_MS = int(START.timestamp() * 1000)
END_MS = int(END.timestamp() * 1000)


@pytest.fixture(autouse=True)
def config(monkeypatch):
    monkeypatch.setattr(homer, "baseUrl", "http://homer.example:8080")
    monkeypatch.setattr(homer, "flavor", "v7")
    monkeypatch.setattr(homer, "profile", "1_call")
    monkeypatch.setattr(homer, "retentionDays", 0)


def blobOf(url):
    """The query string is the JSON blob, minus the trailing '='."""
    query = url.split("?", 1)[1]
    assert query.endswith("="), "the trailing '=' must be emitted explicitly"
    return json.loads(unquote(query[:-1]))


def filtersOf(url):
    return blobOf(url)["param"]["search"]["1_call"]


# ------------------------------------------------------------ exact link

def test_exact_link_shape():
    url = homer.traceUrl("2107293265c8f584671b63541f1f216f", START, END)
    assert url.startswith("http://homer.example:8080/search/result?")
    blob = blobOf(url)
    # "callid" is the short form: the value must be an ARRAY
    assert blob["param"]["search"]["1_call"] == {
        "callid": ["2107293265c8f584671b63541f1f216f"]}
    assert blob["param"]["limit"] == 200
    assert blob["timestamp"]["from"] == START_MS - 60_000
    assert blob["timestamp"]["to"] == END_MS + 60_000
    assert "location" not in blob["param"]      # node stays optional


def test_missing_end_falls_back_to_five_minutes():
    assert blobOf(homer.traceUrl("abc", START, None))["timestamp"]["to"] \
        == START_MS + 300_000 + 60_000


def test_cisco_style_call_id_with_at_sign():
    """Call-IDs of the form xxxx@10.0.0.1 must round-trip unchanged."""
    callId = "0123456789abcdef@10.0.0.1"
    url = homer.traceUrl(callId, START, END)
    assert "@" in url, "'@' is legal in a query string and stays raw"
    assert filtersOf(url)["callid"] == [callId]


@pytest.mark.parametrize("value", [
    "call#with-hash",       # '#' would truncate the link in the browser
    "call with space", "call+plus", "call&amp", "call%percent",
])
def test_breaking_characters_are_escaped(value):
    url = homer.traceUrl(value, START, END)
    assert " " not in url and "#" not in url.split("?", 1)[1]
    assert filtersOf(url)["callid"] == [value]


# ------------------------------------------------------- approximate link

def test_room_link_uses_the_generic_scalar_form():
    url = homer.roomUrl("3.wqpmzrtkcx", START, END)
    # "data_header.*" is the generic form: the value must be a SCALAR
    assert filtersOf(url) == {"data_header.to_user": "3.wqpmzrtkcx"}


def test_room_filter_value_comes_from_the_destination_uri():
    """
    Homer indexes to_user as the user part of the destination URI, prefix
    included ("3.wqpmzrtkcx"), so it is read from the URI rather than rebuilt
    from the room — no per-platform prefix to guess.
    """
    assert homer.roomFilterValue("3.wqpmzrtkcx@visio.sample.org",
                                 "wqpmzrtkcx") == "3.wqpmzrtkcx"
    assert homer.roomFilterValue(None, "wqpmzrtkcx") == "wqpmzrtkcx"   # weaker guess
    assert homer.roomFilterValue("", None) is None


# ----------------------------------------------------- live endpoint link

def test_endpoint_link_uses_the_validated_generic_form():
    """
    from_user alone is silently ignored by Homer; data_header.from_user was
    validated by negative control on our instance (impossible value -> 0 rows).
    """
    url = homer.endpointUrl("test", START, END)
    assert filtersOf(url) == {"data_header.from_user": "test"}
    assert homer.endpointUrl("", START, END) is None


@pytest.mark.parametrize("uri, expected", [
    ("sip:test@sip.sample.org", "test"),
    ("SIP:Test@host", "Test"),
    ("test@host", "test"),
    ("sip:0123456789@10.0.0.1:5060", "0123456789"),
    ("", None), (None, None), ("sip:@host", None),
])
def test_user_part_of_a_sip_uri(uri, expected):
    assert homer.userPart(uri) == expected


# ------------------------------------------------------------ link choice

def call(**overrides):
    base = {"call_id": None, "call_start": START, "call_end": END,
            "destination_uri": None, "room": None}
    base.update(overrides)
    return base


def test_call_id_wins_over_room():
    url, kind = homer.callLink(call(call_id="abc",
                                    destination_uri="3.room@visio.sample.org"))
    assert kind == "exact" and filtersOf(url)["callid"] == ["abc"]


def test_room_used_when_call_id_is_empty():
    url, kind = homer.callLink(call(call_id="",
                                    destination_uri="3.room@visio.sample.org"))
    assert kind == "room"
    assert filtersOf(url) == {"data_header.to_user": "3.room"}


def test_no_link_when_neither_is_usable():
    assert homer.callLink(call()) == (None, None)


# --------------------------------------------------------- no-link cases

def test_no_link_without_base(monkeypatch):
    monkeypatch.setattr(homer, "baseUrl", "")
    assert homer.traceUrl("abc", START, END) is None
    assert homer.callLink(call(call_id="abc")) == (None, None)


def test_no_link_without_start():
    assert homer.traceUrl("abc", None, None) is None


def test_retention_accepts_a_naive_start(monkeypatch):
    """
    The park view parses call_started, a local ISO string with no zone, into a
    naive datetime. With retention on, comparing it with the aware cut-off
    raised TypeError and took /api/gateways down on every poll.
    """
    monkeypatch.setattr(homer, "retentionDays", 7)
    naive = dt.datetime.now() - dt.timedelta(minutes=5)
    assert homer.searchUrl({"callid": ["abc"]}, naive) is not None
    old = dt.datetime.now() - dt.timedelta(days=30)
    assert homer.searchUrl({"callid": ["abc"]}, old) is None


def test_no_link_beyond_retention(monkeypatch):
    monkeypatch.setattr(homer, "retentionDays", 7)
    old = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)
    recent = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)
    assert homer.traceUrl("abc", old, None) is None
    assert homer.traceUrl("abc", recent, None) is not None


def test_unknown_flavor_yields_no_link(monkeypatch):
    monkeypatch.setattr(homer, "flavor", "v42")
    assert homer.traceUrl("abc", START, END) is None


def test_v11_variant(monkeypatch):
    monkeypatch.setattr(homer, "flavor", "v11")
    url = homer.traceUrl("abc@10.0.0.1", START, END)
    assert url.startswith("http://homer.example:8080/?call_id=abc%4010.0.0.1")
    assert url.endswith("#dashboard")
    # the v11 shape has no room search: no link rather than a wrong one
    assert homer.roomUrl("3.room", START, END) is None
