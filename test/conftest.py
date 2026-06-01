import asyncio
import importlib
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    """FastAPI test client for proxy tests."""
    proxy_module = importlib.import_module("deploy.proxyAPI.proxy")
    return TestClient(proxy_module.app)


@pytest.fixture
def redis_mock():
    """Mock Redis interface shared by proxy tests."""
    return Mock(spec=["scan_iter", "get", "set", "delete", "exists","setex"])


@pytest.fixture
def disable_proxy_monitor_gateways(monkeypatch):
    """Désactive monitorGateways sur le module proxy pour les tests."""
    proxy_module = importlib.import_module("deploy.proxyAPI.proxy")

    async def disabled_monitor(*args, **kwargs):
        return None

    monkeypatch.setattr(proxy_module, "monitorGateways", disabled_monitor)
    return proxy_module
