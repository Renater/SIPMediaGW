import asyncio
import os
import sys
import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))
from deploy.proxyAPI import proxy

pytestmark = pytest.mark.usefixtures("disable_proxy_monitor_gateways")


def test_authorize_valid_token():
    request = Mock(headers={"Authorization": "Bearer 1234"})
    assert proxy.authorize(request) is True


def test_authorize_invalid_token():
    request = Mock(headers={"Authorization": "Bearer invalid"})
    assert proxy.authorize(request) is False


def test_authorize_admin_valid_token():
    request = Mock(headers={"Authorization": "Bearer admin-secret-key"})
    assert proxy.authorizeAdmin(request) is True


def test_findAvailableGateway_returns_started_gateway(redis_mock):
    redis_mock.scan_iter.return_value = ["gateway:gw1"]
    redis_mock.get.return_value = "1.2.3.4|started|media|room|start|0|0|None"

    with patch.object(proxy, 'redisClient', redis_mock):
        result = proxy.findAvailableGateway()

    assert result == ["gateway:gw1", "1.2.3.4"]


def test_findAvailableGateway_returns_none_when_no_started_gateway(redis_mock):
    redis_mock.scan_iter.return_value = ["gateway:gw1"]
    redis_mock.get.return_value = "1.2.3.4|stopped|media|room|start|0|0|None"

    with patch.object(proxy, 'redisClient', redis_mock):
        result = proxy.findAvailableGateway()

    assert result is None


def test_updateProgressInfo_updates_redis_mapping(redis_mock):
    parts = ["1.2.3.4", "started", "media", "room"]
    data = {
        "recording_duration": "00:05:30",
        "transcript_progress": "50%",
        "gw_state": "up",
        "call_status": "ROOM",
    }

    with patch.object(proxy, 'redisClient', redis_mock):
        proxy.updateProgressInfo("gw1", parts, data)

    expected = "1.2.3.4|working|media|room|" \
        "|00:05:30|50%|ROOM"
    assert redis_mock.set.call_count == 1
    assert redis_mock.set.call_args[0] == ("gateway:gw1", expected)


def test_getGatewayStatusFromRedis_returns_status(redis_mock):
    redis_mock.get.return_value = "1.2.3.4|working|media|room|start|00:05:30|60%|ROOM"

    with patch.object(proxy, 'redisClient', redis_mock):
        result = proxy.getGatewayStatusFromRedis("gw1")

    assert result["status"] == "success"
    assert result["data"]["gw_id"] == "gw1"
    assert result["data"]["gw_state"] == "working"
    assert result["data"]["call_status"] == "ROOM"


def test_getGatewayStatusFromRedis_returns_none_when_missing(redis_mock):
    redis_mock.get.return_value = None

    with patch.object(proxy, 'redisClient', redis_mock):
        result = proxy.getGatewayStatusFromRedis("gw1")

    assert result is None


def test_adminStatus_requires_admin_token(client, redis_mock):
    redis_mock.scan_iter.return_value = []

    with patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)), \
        patch.object(proxy, 'redisClient', redis_mock):
        response = client.get("/admin/statuses")

    assert response.status_code == 401
    assert response.json()["error"] == "authorization error"

def test_adminStatus_returns_gateways_with_admin_token(client, redis_mock):
    redis_mock.scan_iter.return_value = ["gateway:gw1"]
    redis_mock.get.return_value = "1.2.3.4|working|media|room|start|00:05:30|40%|ROOM"

    with patch.object(proxy, 'redisClient', redis_mock), \
        patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)):
        response = client.get(
        "/admin/statuses",
        headers={"Authorization": "Bearer admin-secret-key"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "gw1": {
            "gateway": "1.2.3.4",
            "status": "working",
            "room": "room",
            "media_duration": "00:05:30",
            "transcript_progress": "40%",
        }
    }


def test_get_asset_file_not_found(client):
    with patch.object(proxy.os.path, 'isfile', return_value=False),\
        patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)):
        response = client.get("/assets/assets.tar.xz")

    assert response.status_code == 404
    assert response.json()['error']["detail"] == "Fichier non trouvé."


def test_fetchAndStoreGatewayStatus_success(redis_mock):
    response = Mock()
    response.json.return_value = {"status": "success", "data": {"gw_state": "up", "call_status": "ROOM"}}

    async_client = AsyncMock()
    async_client.__aenter__.return_value = async_client
    async_client.get.return_value = response

    with patch('deploy.proxyAPI.proxy.httpx.AsyncClient', return_value=async_client), patch.object(proxy, 'redisClient', redis_mock):
        asyncio.run(proxy._fetchAndStoreGatewayStatus("gw1", "127.0.0.1", ["1.2.3.4"]))

    assert redis_mock.set.called is True


def test_fetchAndStoreGatewayStatus_deletes_mapping_on_error(redis_mock):
    response = Mock()
    response.json.return_value = {"status": "error"}

    async_client = AsyncMock()
    async_client.__aenter__.return_value = async_client
    async_client.get.return_value = response

    with patch('deploy.proxyAPI.proxy.httpx.AsyncClient', return_value=async_client), patch.object(proxy, 'redisClient', redis_mock):
        asyncio.run(proxy._fetchAndStoreGatewayStatus("gw1", "127.0.0.1", ["1.2.3.4"]))

    redis_mock.delete.assert_called_once_with("gateway:gw1")


# ----------------------- Authorization Edge Cases ============
def test_authorize_missing_authorization_header():
    request = Mock(headers={})
    assert proxy.authorize(request) is False


def test_authorize_malformed_bearer_header():
    request = Mock(headers={"Authorization": "InvalidBearerFormat"})
    assert proxy.authorize(request) is False


def test_authorizeAdmin_missing_authorization_header():
    request = Mock(headers={})
    assert proxy.authorizeAdmin(request) is False


def test_authorizeAdmin_invalid_token():
    request = Mock(headers={"Authorization": "Bearer invalid-token"})
    assert proxy.authorizeAdmin(request) is False


# ----------------------- updateProgressInfo Edge Cases ============
def test_updateProgressInfo_with_state_down(redis_mock):
    parts = ["1.2.3.4", "started", "media", "room"]
    data = {
        "gw_state": "down",
        "call_status": "IDLE",
    }

    with patch.object(proxy, 'redisClient', redis_mock):
        proxy.updateProgressInfo("gw1", parts, data)

    expected = "1.2.3.4|started|media|room||||IDLE"
    assert redis_mock.set.call_args[0] == ("gateway:gw1", expected)


def test_updateProgressInfo_with_streaming_duration(redis_mock):
    parts = ["1.2.3.4", "started", "media", "room"]
    data = {
        "streaming_duration": "00:10:20",
        "call_status": "STREAMING",
    }

    with patch.object(proxy, 'redisClient', redis_mock):
        proxy.updateProgressInfo("gw1", parts, data)

    expected = "1.2.3.4|started|media|room||00:10:20||STREAMING"
    assert redis_mock.set.call_args[0] == ("gateway:gw1", expected)


def test_updateProgressInfo_extends_parts_list(redis_mock):
    parts = ["1.2.3.4"]  # Short parts list
    data = {
        "recording_duration": "00:05:00",
        "call_status": "ACTIVE",
    }

    with patch.object(proxy, 'redisClient', redis_mock):
        proxy.updateProgressInfo("gw1", parts, data)

    # Should extend parts and add data
    assert redis_mock.set.called


# ----------------------- GET /assets Endpoint ============
def test_get_asset_wrong_filename(client):
    with patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)):
        response = client.get("/assets/wrong_file.txt")

    assert response.status_code == 404
    assert "Fichier non trouvé" in response.json()["error"]["detail"]


def test_get_asset_file_exists(client):
    with patch.object(proxy.os.path, 'isfile', return_value=True), \
        patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)), \
        patch('deploy.proxyAPI.proxy.FileResponse') as mock_file_response:
        
        mock_file_response.return_value = "file_response"
        
        response = client.get("/assets/assets.tar.xz")

    assert response.status_code == 200


# ----------------------- GET /interact Endpoint ============
def test_interact_missing_gw_id_parameter(client):
    with patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)):
        response = client.get("/interact")

    assert response.status_code == 400
    assert "gw_id" in response.json()["error"]["detail"]


def test_interact_gateway_not_found(client, redis_mock):
    redis_mock.get.return_value = None

    with patch.object(proxy, 'redisClient', redis_mock), \
        patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)):
        response = client.get("/interact?gw_id=nonexistent")

    assert response.status_code == 404
    assert "not found" in response.json()["error"]["detail"]


def test_interact_successful_proxy(client, redis_mock):
    redis_mock.get.return_value = "1.2.3.4|working|media|room|start|0|0|None"

    mock_response = Mock()
    mock_response.content = b"<html>Test</html>"
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "text/html"}

    with patch.object(proxy, 'redisClient', redis_mock), \
        patch('deploy.proxyAPI.proxy.proxyToGateway') as mock_proxy, \
        patch.object(proxy, 'monitorGateways', return_value=None):
        
        mock_proxy.return_value = mock_response       
        response = client.get("/interact?gw_id=gw1")

    assert response.status_code == 200


# ----------------------- proxyToGateway Function ============
def test_proxyToGateway_get_request():
    mock_response = AsyncMock()
    mock_response.json.return_value = {"status": "success"}
    
    async_client = AsyncMock()
    async_client.__aenter__.return_value = async_client
    async_client.get.return_value = mock_response

    request = Mock(method="GET")

    with patch('deploy.proxyAPI.proxy.httpx.AsyncClient', return_value=async_client):
        result = asyncio.run(proxy.proxyToGateway("http://test/url", request, {}, None, {}))

    assert result == mock_response


def test_proxyToGateway_post_request():
    mock_response = AsyncMock()
    mock_response.json.return_value = {"status": "success"}
    
    async_client = AsyncMock()
    async_client.__aenter__.return_value = async_client
    async_client.request.return_value = mock_response

    request = Mock(method="POST")

    with patch('deploy.proxyAPI.proxy.httpx.AsyncClient', return_value=async_client):
        result = asyncio.run(proxy.proxyToGateway("http://test/url", request, {}, {"key": "value"}, {}))

    assert result == mock_response


def test_proxyToGateway_timeout():
    async_client = AsyncMock()
    async_client.__aenter__.return_value = async_client
    async_client.get.side_effect = __import__('httpx').ReadTimeout("Timeout")

    request = Mock(method="GET")

    with patch('deploy.proxyAPI.proxy.httpx.AsyncClient', return_value=async_client):
        with pytest.raises(__import__('fastapi').HTTPException) as exc_info:
            asyncio.run(proxy.proxyToGateway("http://test/url", request, {}, None, {}))

    assert exc_info.value.status_code == 504


# ----------------------- POST /start Endpoint ============
def test_start_gateway_missing_token(client):
    with patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)):
        response = client.post("/start", json={"room": "test", "main_app": "jitsi"})

    assert response.status_code == 401


def test_start_gateway_missing_room_parameter(client):
    with patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)):
        response = client.post(
            "/start",
            json={"main_app": "jitsi"},
            headers={"Authorization": "Bearer 1234"}
        )

    assert response.status_code == 400
    assert "room" in response.json()["error"]["detail"]


def test_start_gateway_missing_main_app_parameter(client):
    with patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)):
        response = client.post(
            "/start",
            json={"room": "test"},
            headers={"Authorization": "Bearer 1234"}
        )

    assert response.status_code == 400
    assert "main_app" in response.json()["error"]["detail"]


def test_start_gateway_no_available_gateways(client, redis_mock):
    redis_mock.scan_iter.return_value = []

    with patch.object(proxy, 'redisClient', redis_mock), \
        patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)):
        response = client.post(
            "/start",
            json={"room": "test", "main_app": "jitsi"},
            headers={"Authorization": "Bearer 1234"}
        )

    assert response.status_code == 503
    assert "No available gateways" in response.json()["error"]["detail"]


def test_start_gateway_successful(client, redis_mock):
    redis_mock.scan_iter.return_value = ["gateway:gw1"]
    redis_mock.get.return_value = "1.2.3.4|started|media|None|2024-01-01T00:00:00|0|0|None"

    mock_response = Mock()
    mock_response.json.return_value = {"status": "success", "gw_id": "gw1"}
    mock_response.status_code = 200

    with patch.object(proxy, 'redisClient', redis_mock), \
        patch('deploy.proxyAPI.proxy.proxyToGateway') as mock_proxy, \
        patch.object(proxy, 'monitorGateways', return_value=None):
        
        mock_proxy.return_value = mock_response  
        response = client.post(
            "/start",
            json={"room": "test", "main_app": "jitsi"},
            headers={"Authorization": "Bearer 1234"}
        )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert redis_mock.set.called


def test_start_gateway_error_response(client, redis_mock):
    redis_mock.scan_iter.return_value = ["gateway:gw1"]
    redis_mock.get.return_value = "1.2.3.4|started|media|None|2024-01-01T00:00:00|0|0|None"

    mock_response = AsyncMock()
    mock_response.json.return_value = {"status": "error", "error": {"detail": "Gateway error"}}
    mock_response.status_code = 500

    with patch.object(proxy, 'redisClient', redis_mock), \
        patch('deploy.proxyAPI.proxy.proxyToGateway', return_value=mock_response), \
        patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)):
        response = client.post(
            "/start",
            json={"room": "test", "main_app": "jitsi"},
            headers={"Authorization": "Bearer 1234"}
        )

    assert response.status_code == 503


def test_start_gateway_invalid_json_response(client, redis_mock):
    redis_mock.scan_iter.return_value = ["gateway:gw1"]
    redis_mock.get.return_value = "1.2.3.4|started|media|None|2024-01-01T00:00:00|0|0|None"

    mock_response = AsyncMock()
    mock_response.json.side_effect = ValueError("Invalid JSON")

    with patch.object(proxy, 'redisClient', redis_mock), \
        patch('deploy.proxyAPI.proxy.proxyToGateway', return_value=mock_response), \
        patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)):
        response = client.post(
            "/start",
            json={"room": "test", "main_app": "jitsi"},
            headers={"Authorization": "Bearer 1234"}
        )

    assert response.status_code == 503


# ----------------------- POST /stop Endpoint ============
def test_stop_gateway_missing_token(client):
    with patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)):
        response = client.post("/stop", json={"gw_id": "gw1"})

    assert response.status_code == 401


def test_stop_gateway_missing_gw_id(client):
    with patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)):
        response = client.post(
            "/stop",
            json={},
            headers={"Authorization": "Bearer 1234"}
        )

    assert response.status_code == 400
    assert "gw_id" in response.json()["error"]["detail"]


def test_stop_gateway_not_found(client, redis_mock):
    redis_mock.get.return_value = None

    with patch.object(proxy, 'redisClient', redis_mock), \
        patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)):
        response = client.post(
            "/stop",
            json={"gw_id": "nonexistent"},
            headers={"Authorization": "Bearer 1234"}
        )

    assert response.status_code == 404


def test_stop_gateway_successful(client, redis_mock):
    redis_mock.get.return_value = "1.2.3.4|working|media|room|start|0|0|None"

    mock_response = Mock()
    mock_response.json.return_value = {
        "status": "success",
        "data": {"processing_state": "stopping"}
    }
    mock_response.status_code = 200

    with patch.object(proxy, 'redisClient', redis_mock), \
        patch('deploy.proxyAPI.proxy.proxyToGateway') as mock_proxy, \
        patch.object(proxy, 'monitorGateways', return_value=None):
        
        mock_proxy.return_value = mock_response
        
        response = client.post(
            "/stop",
            json={"gw_id": "gw1"},
            headers={"Authorization": "Bearer 1234"}
        )

    assert response.status_code == 200
    assert redis_mock.set.called


def test_stop_gateway_error_response(client, redis_mock):
    redis_mock.get.return_value = "1.2.3.4|working|media|room|start|0|0|None"

    mock_response = Mock()
    mock_response.json.return_value = {
        "status": "error",
        "data": {"processing_state": "error"}
    }
    mock_response.status_code = 500

    with patch.object(proxy, 'redisClient', redis_mock), \
        patch('deploy.proxyAPI.proxy.proxyToGateway') as mock_proxy, \
        patch.object(proxy, 'monitorGateways', return_value=None):
        
        mock_proxy.return_value = mock_response
        
        response = client.post(
            "/stop",
            json={"gw_id": "gw1"},
            headers={"Authorization": "Bearer 1234"}
        )

    assert response.status_code == 500
    assert response.json()["status"] == "error"


def test_stop_gateway_json_parse_error(client, redis_mock):
    redis_mock.get.side_effect = [
        "1.2.3.4|working|media|room|start|0|0|None",
        "1.2.3.4|working|media|room|start|0|0|None"
    ]

    mock_response = Mock()
    mock_response.json.side_effect = ['bob','']  # Simulate JSON parse error
    mock_response.status_code = 200
    with patch.object(proxy, 'redisClient', redis_mock), \
        patch('deploy.proxyAPI.proxy.proxyToGateway') as mock_proxy, \
        patch.object(proxy, 'monitorGateways', return_value=None):
        
        mock_proxy.return_value = mock_response
        
        response = client.post(
            "/stop",
            json={"gw_id": "gw1"},
            headers={"Authorization": "Bearer 1234"}
        )
    assert response.status_code == 200
    assert response.json()["status"] == "error"


# ----------------------- GET /status Endpoint ============
def test_status_gateway_missing_parameters(client):
    with patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)):
        response = client.get("/status")

    assert response.status_code == 400
    assert "gw_id" in response.json()["error"]["detail"]


def test_status_gateway_by_gw_id(client, redis_mock):
    redis_mock.get.return_value = "1.2.3.4|working|media|room|start|00:05:30|60%|ROOM"

    with patch.object(proxy, 'redisClient', redis_mock), \
        patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)):
        response = client.get("/status?gw_id=gw1")

    assert response.status_code == 200
    assert response.json()["data"]["gw_id"] == "gw1"


def test_status_gateway_by_room(client, redis_mock):
    redis_mock.scan_iter.return_value = ["gateway:gw1"]
    redis_mock.get.return_value = "1.2.3.4|working|media|room|start|00:05:30|60%|ROOM"

    with patch.object(proxy, 'redisClient', redis_mock), \
        patch.object(proxy, 'monitorGateways', return_value=None):
        response = client.get("/status?room=room")

    assert response.status_code == 200
    assert response.json()["status"] == "success"


def test_status_gateway_room_not_found(client, redis_mock):
    redis_mock.scan_iter.return_value = ["gateway:gw1"]
    redis_mock.get.return_value = "1.2.3.4|working|media|other_room|start|0|0|None"

    with patch.object(proxy, 'redisClient', redis_mock), \
        patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)):
        response = client.get("/status?room=nonexistent")

    assert response.status_code == 404


def test_status_gateway_not_found(client, redis_mock):
    redis_mock.get.return_value = None

    with patch.object(proxy, 'redisClient', redis_mock), \
        patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)):
        response = client.get("/status?gw_id=nonexistent")

    assert response.status_code == 404


def test_status_gateway_baresip_type_monitor(client, redis_mock):
    redis_mock.get.side_effect = [
        "1.2.3.4|working|baresip|room|start|0|0|None",  # First call returns baresip
        "1.2.3.4|working|baresip|room|start|00:05:30|60%|ROOM",  # After monitor
        "1.2.3.4|working|baresip|room|start|00:10:30|80%|ROOM"  # After monitor
    ]

    async def mock_monitor(*args, **kwargs):
        pass

    with patch.object(proxy, 'redisClient', redis_mock), \
        patch('deploy.proxyAPI.proxy.monitorOneGateway', side_effect=mock_monitor), \
        patch.object(proxy, 'monitorGateways', return_value=None):
        response = client.get("/status?gw_id=gw1")

    assert response.status_code == 200


def test_status_gateway_baresip_unreachable_after_monitor(client, redis_mock):
    redis_mock.get.side_effect = [
        "1.2.3.4|working|baresip|room|start|0|0|None",  # First call
        None  # After monitor - gateway removed
    ]

    with patch.object(proxy, 'redisClient', redis_mock), \
        patch('deploy.proxyAPI.proxy.monitorOneGateway', return_value=asyncio.coroutine(lambda: None)()), \
        patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)):
        response = client.get("/status?gw_id=gw1")

    assert response.status_code == 404


def test_progress_endpoint_same_as_status(client, redis_mock):
    redis_mock.get.return_value = "1.2.3.4|working|media|room|start|00:05:30|60%|ROOM"

    with patch.object(proxy, 'redisClient', redis_mock), \
        patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)):
        response = client.get("/progress?gw_id=gw1")

    assert response.status_code == 200


# ----------------------- POST /register Endpoint ============
def test_register_gateway_missing_token(client):
    with patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)):
        response = client.post("/register", json={"gw_ip": "1.2.3.4", "gw_id": "gw1"})

    assert response.status_code == 401


def test_register_gateway_missing_gw_ip(client):
    with patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)):
        response = client.post(
            "/register",
            json={"gw_id": "gw1"},
            headers={"Authorization": "Bearer 1234"}
        )

    assert response.status_code == 400


def test_register_gateway_missing_gw_id(client):
    with patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)):
        response = client.post(
            "/register",
            json={"gw_ip": "1.2.3.4"},
            headers={"Authorization": "Bearer 1234"}
        )

    assert response.status_code == 400


def test_register_gateway_new_registration(client, redis_mock):
    redis_mock.get.return_value = None

    with patch.object(proxy, 'redisClient', redis_mock), \
        patch('deploy.proxyAPI.proxy.dt.datetime') as mock_datetime, \
        patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)):
        
        mock_datetime.now.return_value.isoformat.return_value = "2024-01-01T00:00:00"    
        response = client.post(
            "/register",
            json={"gw_ip": "1.2.3.4", "gw_id": "gw1"},
            headers={"Authorization": "Bearer 1234"}
        )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["gw_id"] == "gw1"
    assert redis_mock.set.called


def test_register_gateway_existing_registration(client, redis_mock):
    redis_mock.get.return_value = "1.2.3.4|working|media|room|2024-01-01T00:00:00|00:05:30|60%|ROOM"

    with patch.object(proxy, 'redisClient', redis_mock), \
        patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)):
        response = client.post(
            "/register",
            json={"gw_ip": "5.6.7.8", "gw_id": "gw1", "gw_type": "baresip"},
            headers={"Authorization": "Bearer 1234"}
        )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    # Should preserve existing metrics
    assert redis_mock.set.called


def test_register_gateway_exception(client, redis_mock):
    redis_mock.get.side_effect = Exception("Redis error")

    with patch.object(proxy, 'redisClient', redis_mock), \
        patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)):
        response = client.post(
            "/register",
            json={"gw_ip": "1.2.3.4", "gw_id": "gw1"},
            headers={"Authorization": "Bearer 1234"}
        )

    assert response.status_code == 400


# ----------------------- POST /unregister Endpoint ============
def test_unregister_gateway_missing_token(client):
    with patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)):
        response = client.post("/unregister", json={"gw_id": "gw1"})

    assert response.status_code == 401


def test_unregister_gateway_missing_gw_id(client):
    with patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)):
        response = client.post(
            "/unregister",
            json={},
            headers={"Authorization": "Bearer 1234"}
        )

    assert response.status_code == 400


def test_unregister_gateway_not_found(client, redis_mock):
    redis_mock.exists.return_value = False

    with patch.object(proxy, 'redisClient', redis_mock), \
        patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)):
        response = client.post(
            "/unregister",
            json={"gw_id": "nonexistent"},
            headers={"Authorization": "Bearer 1234"}
        )

    assert response.status_code == 404


def test_unregister_gateway_successful(client, redis_mock):
    redis_mock.exists.return_value = True

    with patch.object(proxy, 'redisClient', redis_mock), \
        patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)):
        response = client.post(
            "/unregister",
            json={"gw_id": "gw1"},
            headers={"Authorization": "Bearer 1234"}
        )

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert redis_mock.delete.called


def test_unregister_gateway_exception(client, redis_mock):
    redis_mock.exists.side_effect = Exception("Redis error")

    with patch.object(proxy, 'redisClient', redis_mock), \
        patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)):
        response = client.post(
            "/unregister",
            json={"gw_id": "gw1"},
            headers={"Authorization": "Bearer 1234"}
        )

    assert response.status_code == 400


# ----------------------- Proxy Endpoints (genericGatewayProxy) ============
def test_command_gateway_missing_gw_id(client):
    with patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)):
        response = client.post(
            "/command",
            json={},
            headers={"Authorization": "Bearer 1234"}
        )

    assert response.status_code == 400


def test_command_gateway_not_found(client, redis_mock):
    redis_mock.get.return_value = None

    with patch.object(proxy, 'redisClient', redis_mock), \
        patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)):
        response = client.post(
            "/command",
            json={"gw_id": "nonexistent"},
            headers={"Authorization": "Bearer 1234"}
        )

    assert response.status_code == 404


def test_command_gateway_stopped(client, redis_mock):
    redis_mock.get.return_value = "1.2.3.4|stopped|media|None|start|0|0|None"

    with patch.object(proxy, 'redisClient', redis_mock), \
        patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)):
        response = client.post(
            "/command",
            json={"gw_id": "gw1", "command": "test"},
            headers={"Authorization": "Bearer 1234"}
        )

    assert response.status_code == 403


def test_command_gateway_successful(client, redis_mock):
    redis_mock.get.return_value = "1.2.3.4|working|media|room|start|0|0|None"

    mock_response = Mock()
    mock_response.json.return_value = {"status": "success"}
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "application/json"}

    with patch.object(proxy, 'redisClient', redis_mock), \
        patch('deploy.proxyAPI.proxy.proxyToGateway') as mock_proxy, \
        patch.object(proxy, 'monitorGateways', return_value=None):
        
        mock_proxy.return_value = mock_response
        
        response = client.post(
            "/command",
            json={"gw_id": "gw1", "command": "test"},
            headers={"Authorization": "Bearer 1234"}
        )

    assert response.status_code == 200


def test_command_gateway_binary_response(client, redis_mock):
    redis_mock.get.return_value = "1.2.3.4|working|media|room|start|0|0|None"

    mock_response = AsyncMock()
    mock_response.json.side_effect = ValueError("Not JSON")
    mock_response.content = b"binary data"
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "image/png"}

    with patch.object(proxy, 'redisClient', redis_mock), \
        patch('deploy.proxyAPI.proxy.proxyToGateway', return_value=mock_response), \
        patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)):
        response = client.post(
            "/command",
            json={"gw_id": "gw1", "command": "test"},
            headers={"Authorization": "Bearer 1234"}
        )

    assert response.status_code == 200


def test_ivrConfig_gateway_successful(client, redis_mock):
    redis_mock.get.return_value = "1.2.3.4|working|media|room|start|0|0|None"

    mock_response = Mock()
    mock_response.json.return_value = {"config": "data"}
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "application/json"}

    with patch.object(proxy, 'redisClient', redis_mock), \
        patch('deploy.proxyAPI.proxy.proxyToGateway') as mock_proxy, \
        patch.object(proxy, 'monitorGateways', return_value=None):
        
        mock_proxy.return_value = mock_response
        
        response = client.get(
            "/ivrConfig?gw_id=gw1",
            headers={"Authorization": "Bearer 1234"}
        )

    assert response.status_code == 200


def test_browsing_gateway_successful(client, redis_mock):
    redis_mock.get.return_value = "1.2.3.4|working|media|room|start|0|0|None"

    mock_response = Mock()
    mock_response.json.return_value = {"browsing": "data"}
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "application/json"}

    with patch.object(proxy, 'redisClient', redis_mock), \
        patch('deploy.proxyAPI.proxy.proxyToGateway') as mock_proxy, \
        patch.object(proxy, 'monitorGateways', return_value=None):
        
        mock_proxy.return_value = mock_response
        
        response = client.get(
            "/browsing?gw_id=gw1",
            headers={"Authorization": "Bearer 1234"}
        )

    assert response.status_code == 200


def test_icon_gateway_successful(client, redis_mock):
    redis_mock.get.return_value = "1.2.3.4|working|media|room|start|0|0|None"

    mock_response = AsyncMock()
    mock_response.json.side_effect = ValueError("Not JSON")
    mock_response.content = b"icon data"
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "image/png"}

    with patch.object(proxy, 'redisClient', redis_mock), \
        patch('deploy.proxyAPI.proxy.proxyToGateway', return_value=mock_response), \
        patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)):
        response = client.get(
            "/icon/test.png?gw_id=gw1",
            headers={"Authorization": "Bearer 1234"}
        )

    assert response.status_code == 200


# ----------------------- monitorOneGateway Function ============
def test_monitorOneGateway(redis_mock):
    redis_mock.get.return_value = "1.2.3.4|working|media|room|start|0|0|None"

    async def mock_fetch(*args, **kwargs):
        pass

    with patch.object(proxy, 'redisClient', redis_mock), \
        patch('deploy.proxyAPI.proxy._fetchAndStoreGatewayStatus', side_effect=mock_fetch):
        asyncio.run(proxy.monitorOneGateway("gw1", "1.2.3.4"))

    assert redis_mock.get.called


# ----------------------- fetchAndStoreGatewayStatus Exception Handling ============
def test_fetchAndStoreGatewayStatus_connection_exception(redis_mock):

    async_client = AsyncMock()
    async_client.__aenter__.return_value = async_client
    async_client.get.side_effect = Exception("Connection error")

    with patch('deploy.proxyAPI.proxy.httpx.AsyncClient', return_value=async_client), \
        patch.object(proxy, 'redisClient', redis_mock):
        asyncio.run(proxy._fetchAndStoreGatewayStatus("gw1", "127.0.0.1", ["1.2.3.4"]))

    redis_mock.delete.assert_called_once_with("gateway:gw1")


# ----------------------- adminStatus with Empty Gateways ============
def test_adminStatus_with_empty_gateway_mapping(client, redis_mock):
    redis_mock.scan_iter.return_value = ["gateway:gw1"]
    redis_mock.get.return_value = None  # Empty mapping

    with patch.object(proxy, 'redisClient', redis_mock), \
        patch.object(proxy, 'monitorGateways', new=AsyncMock(return_value=None)):
        response = client.get(
            "/admin/statuses",
            headers={"Authorization": "Bearer admin-secret-key"}
        )

    assert response.status_code == 200
    assert response.json() == {}


# ----------------------- statusGatewayProxy Endpoint ============
def test_status_proxy_endpoint(client, redis_mock):
    redis_mock.get.return_value = "1.2.3.4|working|media|room|start|0|0|None"

    mock_response = Mock()
    mock_response.json.return_value = {"status": "success"}
    mock_response.status_code = 200
    mock_response.headers = {"content-type": "application/json"}

    with patch.object(proxy, 'redisClient', redis_mock), \
        patch('deploy.proxyAPI.proxy.proxyToGateway') as mock_proxy, \
        patch.object(proxy, 'monitorGateways', return_value=None):
        
        mock_proxy.return_value = mock_response
            
        response = client.get(
            "/status?gw_id=gw1",
            headers={"Authorization": "Bearer 1234"}
        )

    assert response.status_code == 200


# ----------------------- getGatewayStatusFromRedis Edge Cases ============
def test_getGatewayStatusFromRedis_with_full_parts(redis_mock):
    redis_mock.get.return_value = "1.2.3.4|working|media|room|start|00:05:30|60%|ROOM"

    with patch.object(proxy, 'redisClient', redis_mock):
        result = proxy.getGatewayStatusFromRedis("gw1")

    assert result["data"]["gw_id"] == "gw1"
    assert result["data"]["gw_state"] == "working"
    assert result["data"]["room"] == "room"
    assert result["data"]["call_status"] == "ROOM"


# ----------------------- findAvailableGateway with Multiple Gateways ============
def test_findAvailableGateway_returns_first_started(redis_mock):
    redis_mock.scan_iter.return_value = ["gateway:gw1", "gateway:gw2"]
    redis_mock.get.side_effect = [
        "1.2.3.4|stopped|media|room|start|0|0|None",
        "5.6.7.8|started|media|room|start|0|0|None"
    ]

    with patch.object(proxy, 'redisClient', redis_mock):
        result = proxy.findAvailableGateway()

    assert result == ["gateway:gw2", "5.6.7.8"]


# ----------------------- authorize Edge Cases ============
def test_authorize_empty_bearer_token():
    request = Mock(headers={"Authorization": "Bearer "})
    assert proxy.authorize(request) is False


# ----------------------- monitorOneGateway Empty Response ============
def test_monitorOneGateway_empty_redis_response(redis_mock):
    redis_mock.get.return_value = None

    async def mock_fetch(*args, **kwargs):
        pass

    with patch.object(proxy, 'redisClient', redis_mock), \
        patch('deploy.proxyAPI.proxy._fetchAndStoreGatewayStatus', side_effect=mock_fetch):
        asyncio.run(proxy.monitorOneGateway("gw1", "1.2.3.4"))

    assert redis_mock.get.called
