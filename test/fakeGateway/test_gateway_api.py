import pytest
from fastapi.testclient import TestClient
from HTTPLauncher import app

client = TestClient(app)

def test_add_gateway_vm_success():
    params = {
        "gwIp": "192.168.1.100",
        "gwType": "media"
    }
    response = client.post("/gateway/add_gw", json=params)
    print(response.json())
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "gw_id" in data.get("data", {})


def test_start_gateway_success():
    payload = {
        "type": "media",
        "room": "TestRoom",
        "webrtc_domain": {"jitsi": { "name": "Jitsi Meet (meet.jit.si)", "domain": "meet.jit.si" }},
        "gw_id": "gateway:192.168.1.100-gw0",
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
        "type": "",  # Invalid type
        "room": "TestRoom",
        "webrtc_domain": {"renavisio_visio_plus": { "name": "Jitsi Meet (meet.jit.si)", "domain": "meet.jit.si" }},
        "gw_id": "gateway:192.168.1.100-gw0"
    }
    response = client.post("/gateway/start", json=payload)
    assert response.status_code == 200
    data = response.json()
    print(data)
    assert data["status"] == "error"
    assert data.get("error", {}).get("code") == "GW_START_ERROR"


def test_stop_gateway_success():
    payload =  {"gw_id": "gateway:192.168.1.100-gw0"}
    response = client.post("/gateway/stop", json=payload)
    print(response.json())
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "processing_state" in data.get("data", {})
    assert data["data"]["processing_state"] in ["stopped", "finalising"]


def test_status_gateway_success():
    gw_id =  "gateway:192.168.1.100-gw0"
    response = client.get(f"/gateway/{gw_id}/status")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert "task" in data.get("data", {})


def test_command_gateway_success():
    gw_id = "gateway:192.168.1.100-gw0"
    payload = {"action": "ping"}
    response = client.post(f"/gateway/{gw_id}/command", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data.get("data", {}).get("ack") is True



def test_remove_gateway_vm_success():
    #remove the gateway
    remove_params = {
        "gw_id": "gateway:192.168.1.100-gw0"
    }
    response = client.post("/gateway/remove_gw", json=remove_params)
    print(response.json())
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "success"
    assert data.get("data", {}).get("removed") is True