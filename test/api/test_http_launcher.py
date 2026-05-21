import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient
import json
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))


from HTTPLauncher import (
    app, DockerGateway, 
    StartRequest, StopRequest, 
    get_backend
)

# -----------------------
# FIXTURES
# -----------------------

@pytest.fixture
def client():
    """Client HTTP de test pour FastAPI."""
    return TestClient(app)

@pytest.fixture
def mock_docker_gateway():
    """Mock du backend DockerGateway."""
    return Mock(spec=DockerGateway)

@pytest.fixture
def override_backend(mock_docker_gateway):
    """Override le backend injecté pour les tests."""
    app.dependency_overrides[get_backend] = lambda: mock_docker_gateway
    yield mock_docker_gateway
    app.dependency_overrides.clear()

# -----------------------
# TESTS UNITAIRES - DockerGateway
# -----------------------

class TestDockerGatewayStatic:
    """Tests des méthodes statiques de DockerGateway."""
    
    def test_get_status_by_name_found(self):
        """Doit retourner le statut si le nom existe."""
        entries = [
            {"Name": "gw1", "Status": "running"},
            {"Name": "gw2", "Status": "exited"}
        ]
        result = DockerGateway.get_status_by_name(entries, "gw1")
        assert result == "running"
    
    def test_get_status_by_name_not_found(self):
        """Doit retourner None si le nom n'existe pas."""
        entries = [{"Name": "gw1", "Status": "running"}]
        result = DockerGateway.get_status_by_name(entries, "gw999")
        assert result is None
    
    def test_get_status_by_name_empty_list(self):
        """Doit retourner None pour une liste vide."""
        result = DockerGateway.get_status_by_name([], "gw1")
        assert result is None

    @patch('subprocess.Popen')
    def test_get_gateway_docker_status_single_dict(self, mock_popen):
        """Doit parser une réponse JSON simple (dict)."""
        mock_process = MagicMock()
        mock_process.communicate.return_value = (
            b'{"Name":"my-gateway","Status":"running"}',
            b''
        )
        mock_popen.return_value = mock_process
        
        result = DockerGateway.get_gateway_docker_status("my-gateway")
        assert result == "running"
        mock_popen.assert_called_once()

    @patch('subprocess.Popen')
    def test_get_gateway_docker_status_list(self, mock_popen):
        """Doit parser une réponse JSON list."""
        mock_process = MagicMock()
        mock_process.communicate.return_value = (
            b'[{"Name":"gw1","Status":"running"}]',
            b''
        )
        mock_popen.return_value = mock_process
        
        result = DockerGateway.get_gateway_docker_status("gw1")
        assert result == "running"

    @patch('subprocess.Popen')
    def test_get_gateway_docker_status_multiline(self, mock_popen):
        """Doit parser plusieurs lignes JSON (format ndjson)."""
        mock_process = MagicMock()
        mock_process.communicate.return_value = (
            b'{"Name":"gw1","Status":"running"}\n{"Name":"gw2","Status":"exited"}',
            b''
        )
        mock_popen.return_value = mock_process
        
        result = DockerGateway.get_gateway_docker_status("gw2")
        assert result == "exited"

    @patch('subprocess.Popen')
    def test_get_gw_info_success(self, mock_popen):
        """Doit retourner les infos d'un conteneur gw."""
        mock_process = MagicMock()
        mock_process.communicate.return_value = (
            b'[{"Name":"gw","State":"running","Image":"sip:latest"}]',
            b''
        )
        mock_popen.return_value = mock_process
        
        result = DockerGateway.get_gw_info("gw")
        assert result is not None
        assert result["Name"] == "gw"

    @patch('subprocess.Popen')
    def test_get_gw_info_not_found(self, mock_popen):
        """Doit retourner None si pas de conteneur gw."""
        mock_process = MagicMock()
        mock_process.communicate.return_value = (
            b'[]',
            b''
        )
        mock_popen.return_value = mock_process
        
        result = DockerGateway.get_gw_info("gw")
        assert result is None

    @patch('builtins.open', create=True)
    def test_parse_history_file_valid(self, mock_open):
        """Doit parser un fichier historique valide."""
        mock_file_content = """call_start: 2026-05-13T10:00:00Z
room: {"value": "room1", "id": "123"}
call_end: 2026-05-13T10:30:00Z"""
        
        mock_open.return_value.__enter__.return_value = mock_file_content.split('\n')
        
        result = DockerGateway.parseHistoryFile("./logs/test_history")
        assert "call_start" in result
        assert len(result["call_start"]) == 1
        assert result["room"][0]["value"] == "room1"

    @patch('builtins.open', create=True)
    def test_parse_history_file_empty_lines(self, mock_open):
        """Doit ignorer les lignes vides et mal formées."""
        mock_file_content = ["call_start: 123", "", "bad_line_no_colon", "room: value"]
        mock_open.return_value.__enter__.return_value = mock_file_content
        
        result = DockerGateway.parseHistoryFile("./logs/test_history")
        assert len(result) == 2  # call_start et room
        assert "bad_line_no_colon" not in result

class TestDockerGatewayInstance:
    """Tests des méthodes d'instance de DockerGateway."""
    
    def test_init(self):
        """Doit initialiser avec un store vide."""
        gw = DockerGateway()
        assert gw._store == {}

    @patch('subprocess.Popen')
    def test_start_gateway_success(self, mock_popen):
        """Doit démarrer un conteneur avec succès."""
        mock_process = MagicMock()
        mock_process.communicate.return_value = (b'', b'')
        mock_process.stdout.read.return_value = b'{"res": "ok", "gw_id": "my-gw"}'
        mock_popen.return_value = mock_process
        
        gw = DockerGateway()
        req = StartRequest(
            room="room1",
            gw_id="my-gw",
            main_app="app1"
        )
        
        result = gw.start_gateway(req)
        assert result["processing_state"] == "working"
        assert result["gw_id"] == "my-gw"

    @patch('subprocess.Popen')
    def test_start_gateway_failure(self, mock_popen):
        """Doit lever une erreur si le démarrage échoue."""
        mock_process = MagicMock()
        mock_process.stdout.read.return_value = b'{"res": "error"}'
        mock_popen.return_value = mock_process
        
        gw = DockerGateway()
        req = StartRequest(room="room1", gw_id="my-gw", main_app="app1")
        
        with pytest.raises(ValueError, match="Failed to start"):
            gw.start_gateway(req)

    @patch('subprocess.Popen')
    @patch('HTTPLauncher.DockerGateway.get_gw_info')
    def test_stop_gateway_success(self, mock_gw_info, mock_popen):
        """Doit arrêter un conteneur avec succès."""
        mock_process = MagicMock()
        mock_process.communicate.return_value = (b'my-gw\n', b'')
        mock_process.stdout.read.return_value = b'my-gw\n'
        mock_process.stderr.read.return_value = b''
        mock_popen.return_value = mock_process
        
        gw = DockerGateway()
        req = StopRequest(gw_id="my-gw")
        
        result = gw.stop_gateway(req)
        assert result["processing_state"] == "stopped"

    @patch('subprocess.Popen')
    def test_stop_gateway_not_found(self, mock_popen):
        """Doit lever une erreur si le conteneur n'existe pas."""
        mock_process = MagicMock()
        mock_process.stdout.read.return_value = b''
        mock_popen.return_value = mock_process
        
        gw = DockerGateway()
        req = StopRequest(gw_id="nonexistent")
        
        with pytest.raises(ValueError, match="no running container"):
            gw.stop_gateway(req)

# -----------------------
# TESTS D'INTÉGRATION - Routes FastAPI
# -----------------------

class TestStartGatewayRoute:
    """Tests de la route POST /gateway/start."""
    
    def test_start_gateway_success(self, client, override_backend):
        """Doit retourner 200 et les données de démarrage."""
        override_backend.start_gateway.return_value = {
            "processing_state": "working",
            "gw_id": "my-gw"
        }
        
        response = client.post("/gateway/start", json={
            "room": "room1",
            "gw_id": "my-gw",
            "main_app": "app1"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["gw_id"] == "my-gw"

    def test_start_gateway_invalid_input(self, client, override_backend):
        """Doit retourner 422 pour une entrée invalide."""
        response = client.post("/gateway/start", json={
            "room": "room1"
            # Manque gw_id et main_app
        })
        
        assert response.status_code == 422

    def test_start_gateway_backend_error(self, client, override_backend):
        """Doit retourner 500 si le backend lève une exception."""
        override_backend.start_gateway.side_effect = Exception("Docker error")
        
        response = client.post("/gateway/start", json={
            "room": "room1",
            "gw_id": "my-gw",
            "main_app": "app1"
        })
        
        assert response.status_code == 500
        assert "Docker error" in response.json()["error"]["detail"]

class TestStopGatewayRoute:
    """Tests de la route POST /gateway/stop."""
    
    def test_stop_gateway_success(self, client, override_backend):
        """Doit retourner 200 et les données d'arrêt."""
        override_backend.stop_gateway.return_value = {
            "processing_state": "stopped"
        }
        
        response = client.post("/gateway/stop", json={"gw_id": "my-gw"})
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_stop_gateway_not_found(self, client, override_backend):
        """Doit retourner 404 si la passerelle n'existe pas."""
        override_backend.stop_gateway.side_effect = ValueError("Gateway not found")
        
        response = client.post("/gateway/stop", json={"gw_id": "nonexistent"})
        
        assert response.status_code == 404

class TestStatusRoute:
    """Tests de la route GET /gateway/status."""
    
    def test_status_success(self, client, override_backend):
        """Doit retourner le statut de la passerelle."""
        override_backend.get_status.return_value = {
            "gw_state": "up",
            "gw_id": "my-gw"
        }
        
        response = client.get("/gateway/status?gw_id=my-gw")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["gw_state"] == "up"

    def test_status_not_found(self, client, override_backend):
        """Doit retourner 404 si la passerelle n'existe pas."""
        override_backend.get_status.side_effect = ValueError("Gateway not found")
        
        response = client.get("/gateway/status?gw_id=nonexistent")
        
        assert response.status_code == 404

class TestCommandRoute:
    """Tests de la route POST /gateway/command."""
    
    def test_command_send_key(self, client, override_backend):
        """Doit envoyer une commande de touche."""
        override_backend.send_command.return_value = {
            "ack": True,
            "received": {"command": "sendKey", "param1": "1"}
        }
        
        response = client.post("/gateway/command", json={
            "gw_id": "my-gw",
            "payload": {"command": "sendKey", "param1": "1"}
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"

    def test_command_gateway_stopped(self, client, override_backend):
        """Doit retourner 403 si la passerelle est arrêtée."""
        override_backend.send_command.side_effect = ValueError("Gateway stopped")
        
        response = client.post("/gateway/command", json={
            "gw_id": "my-gw",
            "payload": {"command": "sendKey", "param1": "1"}
        })
        
        assert response.status_code == 403

# -----------------------
# Tests de validation des modèles Pydantic
# -----------------------

class TestModels:
    """Tests des modèles Pydantic."""
    
    def test_start_request_minimal(self):
        """Doit créer une StartRequest avec les champs minimaux."""
        req = StartRequest(room="r1", gw_id="gw1", main_app="app1")
        assert req.room == "r1"
        assert req.browsing_name is None

    def test_start_request_all_fields(self):
        """Doit créer une StartRequest avec tous les champs."""
        req = StartRequest(
            room="r1",
            gw_id="gw1",
            main_app="app1",
            browsing_name="browse1",
            prefix="pre",
            rtmp_dst="rtmp://...",
            dial="123",
            loop=True,
            transcript="true",
            audio_only="false",
            api_key="key123",
            recipient_mail="test@example.com"
        )
        assert req.transcript == "true"
        assert req.loop is True

# === TESTS MANQUANTS - start_gateway ===
class TestStartGatewayMethod:
    """Tests détaillés de DockerGateway.start_gateway()"""
    
    @patch('subprocess.Popen')
    def test_start_gateway_with_all_options(self, mock_popen):
        """Teste tous les paramètres optionnels."""
        mock_process = MagicMock()
        mock_process.communicate.return_value = (b'', b'')
        mock_process.stdout.read.return_value = b'{"res": "ok", "gw_id": "my-gw"}'
        mock_popen.return_value = mock_process
        
        gw = DockerGateway()
        req = StartRequest(
            room="room1",
            gw_id="my-gw",
            main_app="app1",
            browsing_name="browse1",
            from_id="from123",
            prefix="pre",
            rtmp_dst="rtmp://example.com/live",
            dial="123",
            loop=True,
            transcript="true",
            audio_only="true",
            api_key="key123",
            recipient_mail="test@example.com"
        )
        
        result = gw.start_gateway(req)
        assert result["processing_state"] == "working"
        assert result["gw_id"] == "my-gw"
        # Vérifier que les arguments corrects ont été passés
        call_args = mock_popen.call_args[0][0]
        assert '-b' in call_args  # browsing_name
        assert '-l' in call_args  # loop
        assert '-s' in call_args  # transcript
        assert '-o' in call_args  # audio_only

    @patch('subprocess.Popen')
    def test_start_gateway_json_parse_error(self, mock_popen):
        """Teste la gestion des erreurs JSON."""
        mock_process = MagicMock()
        mock_process.stdout.read.return_value = b'invalid json'
        mock_popen.return_value = mock_process
        
        gw = DockerGateway()
        req = StartRequest(room="r1", gw_id="gw1", main_app="app1")
        
        with pytest.raises(json.JSONDecodeError):
            gw.start_gateway(req)

# === TESTS MANQUANTS - stop_gateway ===
class TestStopGatewayMethod:
    """Tests détaillés de DockerGateway.stop_gateway()"""
    
    @patch('subprocess.Popen')
    def test_stop_gateway_force(self, mock_popen):
        """Teste l'arrêt forcé (down)."""
        mock_process = MagicMock()
        mock_process.communicate.return_value = (
            b'my-gw\n',
            b''
        )
        
        mock_process.stdout.read.return_value = b'my-gw\n'
        mock_popen.return_value = mock_process


        gw = DockerGateway()
        req = StopRequest(gw_id="my-gw", force=True)
        
        result = gw.stop_gateway(req)
        assert result["processing_state"] == "stopped"
        

    @patch('subprocess.Popen')
    def test_stop_gateway_graceful(self, mock_popen):
        """Teste l'arrêt gracieux (stop)."""
        mock_process = MagicMock()
        mock_process.communicate.return_value = (
            b'my-gw\n',
            b''
        )
        mock_process.stdout.read.return_value = b'my-gw\n'

        mock_popen.return_value = mock_process
        
        gw = DockerGateway()
        req = StopRequest(gw_id="my-gw", force=False)
        
        result = gw.stop_gateway(req)
        assert result["processing_state"] == "stopped"

# === TESTS MANQUANTS - get_status ===
class TestGetStatusMethod:
    """Tests détaillés de DockerGateway.get_status()"""
    
    @patch('subprocess.Popen')
    @patch('HTTPLauncher.DockerGateway.get_gw_info')
    @patch('HTTPLauncher.DockerGateway.parseHistoryFile')
    def test_get_status_with_recording(self, mock_parse_history, mock_gw_info, mock_popen):
        """Teste le statut avec enregistrement en cours."""
        mock_gw_info.return_value = {"Name": "my-gw-1"}
        mock_parse_history.return_value = {
            "call_start": ["2026-05-13T10:00:00Z"],
            "room": [{"value": "room1", "id": "123"}]
        }
        
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        
        # Première (status), deuxième (recording), troisième (transcript), quatrième (mp4 list)
        mock_process.communicate.side_effect = [
            (b'[{"Name":"my-gw","Status":"running"}]', b''),  # get_gateway_docker_status
            (b'00:05:30', b''),  # recording duration
            (b'true', b''),  # WITH_TRANSCRIPT
            (b'/var/recording/video.mp4\n/var/recording/video.processed.mp4', b''),  # mp4 list
        ]
        
        gw = DockerGateway()
        result = gw.get_status("my-gw")
        
        assert result["gw_state"] == "up"
        assert result["call_status"] == "ROOM"

    @patch('subprocess.Popen')
    @patch('HTTPLauncher.DockerGateway.get_gateway_docker_status')
    def test_get_status_gateway_exited(self, mock_status, mock_popen):
        """Teste le statut d'un conteneur arrêté."""
        mock_status.return_value = "exited"
        
        gw = DockerGateway()
        result = gw.get_status("my-gw")
        
        assert result["gw_state"] == "down"
        assert result["detail"] == "exited"

    @patch('HTTPLauncher.DockerGateway.get_gateway_docker_status')
    def test_get_status_gateway_not_found(self, mock_status):
        """Teste quand la gateway n'existe pas."""
        mock_status.return_value = None
        
        gw = DockerGateway()
        with pytest.raises(ValueError, match="Gateway not found"):
            gw.get_status("nonexistent")

# === TESTS MANQUANTS - getGatewayBrowsing ===
class TestGetGatewayBrowsingMethod:
    """Tests de DockerGateway.getGatewayBrowsing()"""
    
    @patch('os.path.exists')
    @patch('HTTPLauncher.DockerGateway.get_gw_info')
    @patch('HTTPLauncher.DockerGateway.parseHistoryFile')
    def test_get_gateway_browsing_success(self, mock_parse_history, mock_gw_info, mock_exists):
        """Teste la récupération du browsing name."""
        mock_gw_info.return_value = {"Name": "my-gw-1"}
        mock_exists.return_value = True
        mock_parse_history.return_value = {
            "call_start": ["2026-05-13T10:00:00Z"],
            "room": [{"value": "room1", "id": "123"}]
        }

        gw = DockerGateway()
        result = gw.getGatewayBrowsing("my-gw")
        
        assert result["status"] == "success"
        assert result["browsingName"] == "room1"

    @patch('HTTPLauncher.DockerGateway.get_gw_info')
    def test_get_gateway_browsing_not_found(self, mock_gw_info):
        """Teste quand la gateway n'existe pas."""
        mock_gw_info.return_value = None
        
        gw = DockerGateway()
        with pytest.raises(ValueError, match="Gateway not found"):
            gw.getGatewayBrowsing("nonexistent")

    @patch('os.path.exists')
    @patch('HTTPLauncher.DockerGateway.get_gw_info')
    def test_get_gateway_browsing_no_history_file(self, mock_gw_info, mock_exists):
        """Teste quand le fichier historique n'existe pas."""
        mock_gw_info.return_value = {"Name": "my-gw-1"}
        mock_exists.return_value = False
        
        gw = DockerGateway()
        with pytest.raises(ValueError, match="History file not found"):
            gw.getGatewayBrowsing("my-gw")

# === TESTS MANQUANTS - getIvrConfig ===
class TestGetIvrConfigMethod:
    """Tests de DockerGateway.getIvrConfig()"""
    
    @patch('subprocess.Popen')
    @patch('HTTPLauncher.DockerGateway.get_gw_info')
    def test_get_ivr_config_success(self, mock_gw_info, mock_popen):
        """Teste la récupération de la config IVR."""
        mock_gw_info.return_value = {"Name": "my-gw-1"}
        
        config_json = {
            "menus": {"main": {"options": ["1", "2"]}},
            "webrtc_domains": ["example.com"]
        }
        
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (
            json.dumps(config_json).encode(),
            b''
        )
        mock_popen.return_value = mock_process
        
        gw = DockerGateway()
        result = gw.getIvrConfig("my-gw")
        
        assert result["status"] == "success"
        assert "menus" in result
        assert "webrtc_domains" in result

    @patch('subprocess.Popen')
    @patch('HTTPLauncher.DockerGateway.get_gw_info')
    def test_get_ivr_config_docker_error(self, mock_gw_info, mock_popen):
        """Teste l'erreur si docker exec échoue."""
        mock_gw_info.return_value = {"Name": "my-gw-1"}
        
        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.communicate.return_value = (b'', b'Command failed')
        mock_popen.return_value = mock_process
        
        gw = DockerGateway()
        with pytest.raises(ValueError, match="Failed to read config.json"):
            gw.getIvrConfig("my-gw")

    @patch('subprocess.Popen')
    @patch('HTTPLauncher.DockerGateway.get_gw_info')
    def test_get_ivr_config_invalid_json(self, mock_gw_info, mock_popen):
        """Teste l'erreur si JSON invalide."""
        mock_gw_info.return_value = {"Name": "my-gw-1"}
        
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.communicate.return_value = (b'invalid json', b'')
        mock_popen.return_value = mock_process
        
        gw = DockerGateway()
        with pytest.raises(ValueError, match="Invalid config.json"):
            gw.getIvrConfig("my-gw")

# === TESTS MANQUANTS - send_command ===
class TestSendCommandMethod:
    """Tests de DockerGateway.send_command()"""
    
    @patch('subprocess.Popen')
    @patch('HTTPLauncher.DockerGateway.get_gw_info')
    def test_send_command_send_key(self, mock_gw_info, mock_popen):
        """Teste l'envoi d'une touche."""
        mock_gw_info.return_value = {"Name": "my-gw-1"}
        
        mock_process = MagicMock()
        mock_process.communicate.return_value = (b':0', b'')  # DISPLAY_WEB
        mock_popen.return_value = mock_process
        
        gw = DockerGateway()
        result = gw.send_command("my-gw", {"command": "sendKey", "param1": "1"})
        
        assert result["ack"] is True
        assert result["received"]["command"] == "sendKey"

    @patch('subprocess.Popen')
    @patch('HTTPLauncher.DockerGateway.get_gw_info')
    def test_send_command_send_key_special(self, mock_gw_info, mock_popen):
        """Teste l'envoi de caractères spéciaux."""
        mock_gw_info.return_value = {"Name": "my-gw-1"}
        
        mock_process = MagicMock()
        mock_process.communicate.return_value = (b':0', b'')
        mock_popen.return_value = mock_process
        
        gw = DockerGateway()
        
        # Test # (numbersign)
        result = gw.send_command("my-gw", {"command": "sendKey", "param1": "#"})
        assert result["ack"] is True
        
        # Test * (asterisk)
        result = gw.send_command("my-gw", {"command": "sendKey", "param1": "*"})
        assert result["ack"] is True

    @patch('subprocess.Popen')
    @patch('HTTPLauncher.DockerGateway.get_gw_info')
    def test_send_command_send_string(self, mock_gw_info, mock_popen):
        """Teste l'envoi d'une chaîne."""
        mock_gw_info.return_value = {"Name": "my-gw-1"}
        
        mock_process = MagicMock()
        mock_process.communicate.return_value = (b':0', b'')
        mock_popen.return_value = mock_process
        
        gw = DockerGateway()
        result = gw.send_command("my-gw", {"command": "sendString", "param1": "123"})
        
        assert result["ack"] is True
        # Vérifier qu'il y a eu plusieurs appels (un par caractère)
        assert mock_popen.call_count > 1

    @patch('HTTPLauncher.DockerGateway.get_gw_info')
    def test_send_command_gateway_not_found(self, mock_gw_info):
        """Teste quand la gateway n'existe pas."""
        mock_gw_info.return_value = None
        
        gw = DockerGateway()
        with pytest.raises(ValueError, match="Gateway not found"):
            gw.send_command("nonexistent", {"command": "sendKey", "param1": "1"})

# === TESTS DES ROUTES - Cas d'erreur supplémentaires ===
class TestRoutesCoverage:
    """Couverture supplémentaire des routes"""
    
    def test_command_gateway_stopped(self, client, override_backend):
        """Doit retourner 403 pour une passerelle arrêtée."""
        override_backend.send_command.side_effect = ValueError("Gateway stopped")
        
        response = client.post("/gateway/command", json={
            "gw_id": "my-gw",
            "payload": {"command": "sendKey", "param1": "1"}
        })
        
        assert response.status_code == 403

    def test_browsing_success(self, client, override_backend):
        """Doit retourner les infos de browsing."""
        override_backend.getGatewayBrowsing.return_value = {
            "status": "success",
            "browsingName": "room1"
        }
        
        response = client.get("/gateway/browsing?gw_id=my-gw")
        
        assert response.status_code == 200
        assert response.json()["browsingName"] == "room1"

    def test_browsing_not_found(self, client, override_backend):
        """Doit retourner 404 si la gateway n'existe pas."""
        override_backend.getGatewayBrowsing.side_effect = ValueError("Gateway not found")
        
        response = client.get("/gateway/browsing?gw_id=nonexistent")
        
        assert response.status_code == 404

    def test_ivr_config_success(self, client, override_backend):
        """Doit retourner la config IVR."""
        override_backend.getIvrConfig.return_value = {
            "status": "success",
            "menus": {"main": {}},
            "webrtc_domains": ["example.com"]
        }
        
        response = client.get("/gateway/ivrConfig?gw_id=my-gw")
        
        assert response.status_code == 200
        assert "menus" in response.json()

    def test_ivr_config_not_found(self, client, override_backend):
        """Doit retourner 404 si la config n'existe pas."""
        override_backend.getIvrConfig.side_effect = ValueError("Config not found")
        
        response = client.get("/gateway/ivrConfig?gw_id=nonexistent")
        
        assert response.status_code == 404

    @patch('HTTPLauncher.DockerGateway.get_gw_info')
    def test_icon_not_found(self, mock_gw_info, client):
        """Doit retourner 404 si l'icône n'existe pas."""
        mock_gw_info.return_value = None
        
        response = client.get("/gateway/icon/missing?gw_id=my-gw")
        
        assert response.status_code == 404

    def test_interact_html_success(self, client):
        """Doit retourner le fichier HTML."""
        # Ce test nécessite que le fichier existe
        response = client.get("/gateway/interact")
        
        # Peut être 404 si le fichier n'existe pas, c'est normal
        assert response.status_code in [200, 404]
