"""
The proxy calls each gateway's launcher at the address that the gateway
registered (HOST_IP:GW_API_PORT). GW_API_SCHEME chooses http, the default, or
https, for launchers behind a TLS reverse proxy that the proxy reaches over the
internet.
"""
import asyncio
import json
import os
import subprocess
import sys
from unittest.mock import AsyncMock, Mock, patch

import pytest

from deploy.proxyAPI import proxy

pytestmark = pytest.mark.usefixtures("disable_proxy_monitor_gateways")

REPO = os.path.normpath(os.path.join(os.path.dirname(__file__), "../.."))
ADDRESS = "node1.example.org:443"
TOKEN = {"Authorization": "Bearer 1234"}


def gateway(state):
    return json.dumps({"gw_ip": ADDRESS, "gw_state": state, "gw_type": "baresip", "room": None,
                       "start_time": "2026-01-01T00:00:00", "browsing": None})


def answer(body):
    response = Mock()
    response.json.return_value = body
    response.status_code = 200
    return response


@pytest.fixture(params=["http", "https"])
def scheme(request):
    with patch.object(proxy, "gwApiScheme", request.param):
        yield request.param


@pytest.mark.parametrize("env, expected", [
    ({}, "http"), ({"GW_API_SCHEME": ""}, "http"), ({"GW_API_SCHEME": "https"}, "https"),
])
def test_the_scheme_comes_from_gw_api_scheme(env, expected):
    clean = {k: v for k, v in os.environ.items() if k != "GW_API_SCHEME"}
    clean.update(env)
    out = subprocess.run(
        [sys.executable, "-c", "from deploy.proxyAPI import proxy; print(proxy.gatewayUrl('gw:8100', 'status'))"],
        cwd=REPO, env=clean, capture_output=True, text=True, timeout=60, check=False)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == f"{expected}://gw:8100/gateway/status"


def test_the_status_is_fetched_with_the_scheme(scheme, redis_mock):
    client = AsyncMock()
    client.__aenter__.return_value = client
    client.get.return_value = answer({"status": "success", "data": {"gw_state": "up"}})
    with patch("deploy.proxyAPI.proxy.httpx.AsyncClient", return_value=client), \
            patch.object(proxy, "redisClient", redis_mock):
        asyncio.run(proxy._fetchAndStoreGatewayStatus("gw1", ADDRESS, {"gw_ip": ADDRESS}))
    assert client.get.call_args.args[0] == f"{scheme}://{ADDRESS}/gateway/status"


def test_start_calls_the_gateway_with_the_scheme(scheme, client, redis_mock):
    redis_mock.scan_iter.return_value = ["gateway:gw1"]
    redis_mock.get.return_value = gateway("created")
    with patch.object(proxy, "redisClient", redis_mock), \
            patch("deploy.proxyAPI.proxy.proxyToGateway", return_value=answer({"status": "success"})) as relay:
        response = client.post("/start", json={"room": "room1", "main_app": "baresip", "browsing": "edumeet"},
                               headers=TOKEN)
    assert response.status_code == 200
    assert relay.call_args.args[0] == f"{scheme}://{ADDRESS}/gateway/start"


def test_stop_calls_the_gateway_with_the_scheme(scheme, client, redis_mock):
    redis_mock.get.return_value = gateway("started")
    with patch.object(proxy, "redisClient", redis_mock), \
            patch("deploy.proxyAPI.proxy.proxyToGateway",
                  return_value=answer({"status": "success", "data": {"processing_state": "stopping"}})) as relay:
        response = client.post("/stop", json={"gw_id": "gw1"}, headers=TOKEN)
    assert response.status_code == 200
    assert relay.call_args.args[0] == f"{scheme}://{ADDRESS}/gateway/stop"


@pytest.mark.parametrize("method, path, endpoint", [
    ("post", "/command", "command"),
    ("get", "/ivrConfig?gw_id=gw1", "ivrConfig"),
])
def test_phone_requests_go_to_the_gateway_with_the_scheme(scheme, client, redis_mock, method, path, endpoint):
    redis_mock.get.return_value = gateway("started")
    with patch.object(proxy, "redisClient", redis_mock), \
            patch("deploy.proxyAPI.proxy.proxyToGateway", return_value=answer({"status": "success"})) as relay:
        if method == "post":
            response = client.post(path, json={"gw_id": "gw1", "command": "interact", "key": "1"})
        else:
            response = client.get(path)
    assert response.status_code == 200
    assert relay.call_args.args[0] == f"{scheme}://{ADDRESS}/gateway/{endpoint}"
