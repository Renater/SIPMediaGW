"""Pool sampler: counting by state, and one failure never stopping the loop."""
import asyncio

import pytest

import sampler


def gateways(*states):
    return {"gateways": [{"state": s} for s in states]}


def test_counts_by_state(monkeypatch):
    stored = {}

    async def fakeFetch():
        return gateways("free", "idle", "idle", "ivr", "call", "call", "call", "other")

    monkeypatch.setattr(sampler, "fetchStatuses", fakeFetch)
    monkeypatch.setattr(sampler, "_store", lambda sample: stored.update(sample))
    sample = asyncio.run(sampler.sampleOnce())

    assert (sample["free"], sample["idle"], sample["ivr"], sample["in_call"]) == (1, 2, 1, 3)
    assert stored["in_call"] == 3          # "call" state lands in the in_call column
    assert sample["ts"].tzinfo is not None # stored as an aware UTC instant


def test_empty_pool_is_a_valid_sample(monkeypatch):
    async def fakeFetch():
        return gateways()
    monkeypatch.setattr(sampler, "fetchStatuses", fakeFetch)
    monkeypatch.setattr(sampler, "_store", lambda sample: None)
    sample = asyncio.run(sampler.sampleOnce())
    assert sample["idle"] == sample["ivr"] == sample["in_call"] == 0


def test_loop_survives_a_failing_sample(monkeypatch):
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("proxy down")
        if calls["n"] >= 3:
            raise asyncio.CancelledError()   # stop the test loop
        return {"free": 0, "idle": 1, "ivr": 0, "in_call": 0}

    async def noSleep(_):
        return None

    monkeypatch.setattr(sampler, "sampleOnce", flaky)
    monkeypatch.setattr(sampler.asyncio, "sleep", noSleep)
    monkeypatch.setattr(sampler, "intervalSeconds", 1)
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(sampler.run())
    assert calls["n"] == 3                 # failed once, sampled once, then cancelled


def test_disabled_when_interval_is_zero(monkeypatch):
    def never():
        raise AssertionError("sampled although disabled")

    monkeypatch.setattr(sampler, "intervalSeconds", 0)
    monkeypatch.setattr(sampler, "sampleOnce", never)
    assert asyncio.run(sampler.run()) is None             # returns at once, without sampling
