"""monitorGateways keeps going: a bad entry is skipped on its own, and a
failing cycle does not end the task. The other proxy tests replace the
monitor (pytestmark in test_proxy.py); this file tests the real one."""
import asyncio
import os
import sys
from unittest.mock import AsyncMock, Mock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from deploy.proxyAPI import proxy


class _StopLoop(Exception):
    pass


def _run_cycles(n):
    """Run the monitor for n cycles: the n-th sleep ends it."""
    calls = {"n": 0}

    async def fake_sleep(_):
        calls["n"] += 1
        if calls["n"] >= n:
            raise _StopLoop

    with patch.object(proxy.asyncio, "sleep", new=fake_sleep):
        with pytest.raises(_StopLoop):
            asyncio.run(proxy.monitorGateways(0))


def test_an_unreadable_entry_does_not_hide_the_next_ones():
    entries = {
        "gateway:old": "1.2.3.4|free",               # pre-#97 format: gwLoad gives {}
        "gateway:good": '{"gw_ip": "5.6.7.8", "gw_state": "free"}',
    }
    redis = Mock(spec=["scan_iter", "get"])
    redis.scan_iter.return_value = list(entries)
    redis.get.side_effect = entries.get
    fetch = AsyncMock()
    with patch.object(proxy, "redisClient", redis), \
         patch.object(proxy, "_fetchAndStoreGatewayStatus", new=fetch):
        _run_cycles(1)
    fetch.assert_awaited_once()
    assert fetch.await_args.args[:2] == ("good", "5.6.7.8")


def test_an_entry_that_raises_does_not_hide_the_next_ones():
    redis = Mock(spec=["scan_iter", "get"])
    redis.scan_iter.return_value = ["gateway:a", "gateway:b"]
    redis.get.return_value = '{"gw_ip": "5.6.7.8"}'
    fetch = AsyncMock(side_effect=[RuntimeError("boom"), None])
    with patch.object(proxy, "redisClient", redis), \
         patch.object(proxy, "_fetchAndStoreGatewayStatus", new=fetch):
        _run_cycles(1)
    assert fetch.await_count == 2


def test_a_failing_cycle_does_not_end_the_task():
    redis = Mock(spec=["scan_iter", "get"])
    redis.scan_iter.side_effect = [ConnectionError("redis down"), ["gateway:a"]]
    redis.get.return_value = '{"gw_ip": "5.6.7.8"}'
    fetch = AsyncMock()
    with patch.object(proxy, "redisClient", redis), \
         patch.object(proxy, "_fetchAndStoreGatewayStatus", new=fetch):
        _run_cycles(2)
    fetch.assert_awaited_once()
