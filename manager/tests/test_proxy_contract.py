"""
The proxyAPI contract, read from a real /admin/statuses body rather than from
entries already normalised: tests/fixtures/admin_statuses.json is the shape
deploy/proxyAPI/proxy.py produces (its own suite pins it, gwFields and
deriveState), with one gateway per state the proxy can derive. A key renamed
or a state added on the proxy side shows up here, not as an empty column.
"""

import asyncio
import datetime as dt
import json
from pathlib import Path

import httpx
import pytest

import proxyapi
import sampler

REAL_CLIENT = httpx.AsyncClient
FIXTURE = json.loads((Path(__file__).resolve().parent / "fixtures" / "admin_statuses.json").read_text())

# What proxy.py's adminStatus() writes for every gateway (gwFields + state + pairing_code).
PROXY_KEYS = {"gateway", "type", "status", "state", "room", "media_duration", "transcript_progress",
              "browsing", "peer_uri", "peer_name", "call_started", "pairing_code"}
# What the Manager hands to the sampler and the route, per gateway.
MANAGER_KEYS = {"state", "gw_id", "ip", "type", "status", "room", "browsing", "peer_uri", "peer_name",
                "call_started", "call_seconds", "transcript_progress", "pairing_code"}
STATES = {"free", "idle", "ivr", "call", "gone", "other"}


@pytest.fixture
def served(monkeypatch):
    """fetchStatuses() reads the fixture over a real httpx client, no network."""
    seen = {}

    def handler(request):
        seen["auth"] = request.headers.get("authorization")
        seen["path"] = request.url.path
        return httpx.Response(200, json=FIXTURE)

    transport = httpx.MockTransport(handler)
    monkeypatch.setattr(proxyapi.httpx, "AsyncClient", lambda **kw: REAL_CLIENT(transport=transport, **kw))
    monkeypatch.setitem(proxyapi.source("proxyapi"), "token", "admin-token-test")
    return seen


def test_the_fixture_is_the_proxy_s_shape():
    assert all(set(entry) == PROXY_KEYS for entry in FIXTURE.values())
    assert {entry["state"] for entry in FIXTURE.values()} == STATES, "one gateway per state the proxy derives"


def test_every_gateway_comes_through_with_the_manager_s_keys(served):
    pool = asyncio.run(proxyapi.fetchStatuses())
    assert served["path"] == "/admin/statuses" and served["auth"] == "Bearer admin-token-test"
    assert [g["gw_id"] for g in pool["gateways"]] == sorted(FIXTURE)
    assert all(set(g) == MANAGER_KEYS for g in pool["gateways"])
    assert {g["state"] for g in pool["gateways"]} == STATES, "a state must never be lost on the way"
    dt.datetime.fromisoformat(pool["generated_at"])


def test_the_none_literals_of_an_old_entry_are_read_as_absent(served):
    pool = asyncio.run(proxyapi.fetchStatuses())
    stale = next(g for g in pool["gateways"] if g["gw_id"] == "gw7")
    assert stale["room"] is None and stale["peer_uri"] is None and stale["call_seconds"] is None
    assert stale["state"] == "other"


def test_call_seconds_come_from_a_utc_instant(served, monkeypatch):
    pool = asyncio.run(proxyapi.fetchStatuses())
    inCall = next(g for g in pool["gateways"] if g["gw_id"] == "gw1")
    assert isinstance(inCall["call_seconds"], int) and inCall["call_seconds"] >= 0
    # The fixture's instant is in the past: a value of a few minutes would mean
    # the Z suffix was read as local time.
    assert inCall["call_seconds"] > 3600
    idle = next(g for g in pool["gateways"] if g["gw_id"] == "gw3")
    assert idle["call_seconds"] is None


def test_the_sampler_counts_what_the_proxy_says(served, monkeypatch):
    stored = {}
    monkeypatch.setattr(sampler, "_store", lambda sample: stored.update(sample))
    sample = asyncio.run(sampler.sampleOnce())
    # gw1 call, gw2 ivr, gw3 idle, gw4 free, gw5 recording in call, gw6 gone, gw7 other
    assert (sample["free"], sample["idle"], sample["ivr"], sample["in_call"]) == (1, 1, 1, 2)
    assert stored["in_call"] == 2, "gone and other are not provisioned capacity"
