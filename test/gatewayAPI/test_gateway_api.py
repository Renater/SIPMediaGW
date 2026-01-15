import pytest
import sys
import os
from pathlib import Path
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../..')));

from HTTPLauncher import app

client = TestClient(app)

GW_ID = "gw_test_01"

# Set environment variable to indicate test mode
os.environ["MODE"] = "fake"

def test_start_gateway_success():
    payload = {
        "type": "media",
        "room": "TestRoom",
        "webrtc_domain": {"jitsi": { "name": "Jitsi Meet (meet.jit.si)", "domain": "meet.jit.si" }},
        "gw_id": GW_ID,
        "fromId": "user1",
        "prefix": "",
        "rtmpDst": "rtmp://example.com/live",
        "dial": "sip:user2@example.com",
        "loop": False,
        "transcript": "true",
        "audioOnly": "false",
        "apiKey": "secret_api_key",
        "recipientMail": "user1@example.com"
    }
    response = client.post("/gateway/start", json=payload)
    assert response.status_code == 200
    data = response.json()
    print(data)
    assert data["status"] == "success"
    assert "processing_state" in data.get("data", {})
    assert data["data"]["processing_state"] in ["stopped", "working"]


def test_start_gateway_failure():
    payload = {
        "room": "TestRoom",
        "webrtc_domain": {"renavisio_visio_plus": { "name": "Jitsi Meet (meet.jit.si)", "domain": "meet.jit.si" }},
        "gw_id": GW_ID
    }
    response = client.post("/gateway/start", json=payload)
    assert response.status_code != 200
    data = response.json()
    print(data)
    assert data["status"] == "error"
    assert data["error"] == "Invalid input"


def test_status_gateway_success():
    response = client.get(f"/gateway/status?gw_id={GW_ID}")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"


def test_command_gateway_success():
    payload = {"gw_id": GW_ID, "payload": {"action": "ping"}}
    response = client.post(f"/gateway/command", json=payload)
    data = response.json()
    print(data)
    assert response.status_code == 200
   
    assert data["status"] == "success"


def test_start_gateway_validation_error():
    # missing required fields should return 422
    response = client.post("/gateway/start", json={})
    assert response.status_code == 422

def test_stop_gateway_success():
    payload =  {"gw_id": GW_ID}
    response = client.post("/gateway/stop", json=payload)
    print(response.json())
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "processing_state" in data.get("data", {})
    assert data["data"]["processing_state"] in ["stopped", "finalising"]


def test_command_gateway_forbidden_after_stop():
    payload = {"gw_id": GW_ID, "payload": {"action": "ping"}}
    response = client.post(f"/gateway/command", json=payload)
    assert response.status_code == 403


def test_status_gateway_success_after_stop():
    response = client.get(f"/gateway/status?gw_id={GW_ID}")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data.get("data", {}).get("processing_state") == "stopped"