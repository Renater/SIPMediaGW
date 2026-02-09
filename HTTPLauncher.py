# Single-file FastAPI app with pluggable backend (DockerGateway / FakeGateway)
# - introduces MediaBackend ABC
# - selects backend via MODE env var (MODE=fake -> FakeGateway)
# - uses FastAPI Depends for injection
# - keeps endpoints and response models compatible with previous behavior

from fastapi import FastAPI, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError, HTTPException
from pydantic import BaseModel, RootModel, field_validator
from typing import Optional, Dict, Any
from abc import ABC, abstractmethod
import os
import datetime as dt
import subprocess
import json
import argparse
import uvicorn
from functools import lru_cache

app = FastAPI(title="SIP Media Gateway API", version="1.0.0")


# -----------------------
# Models
# -----------------------
class ErrorBlock(BaseModel):
    code: Optional[str] = None
    message: Optional[str] = None

class BaseResponse(BaseModel):
    status: str              # success / error
    error: Optional[ErrorBlock] = None

# START
class ProviderConfig(BaseModel):
    name: str
    domain: str

class WebRTCDomain(RootModel[Dict[str, ProviderConfig]]):
    @field_validator("root")
    def only_one_provider(cls, value):
        if len(value) != 1:
            raise ValueError("webrtc_domain must contain exactly one provider")
        return value

class StartRequest(BaseModel):
    room: str
    gw_id: str
    main_app: str
    webrtc_domain: Optional[WebRTCDomain] = None
    from_id: Optional[str] = None
    prefix: Optional[str] = None
    rtmp_dst: Optional[str] = None
    dial: Optional[str] = None
    loop: Optional[bool] = None
    transcript: Optional[str] = None
    audio_only: Optional[str] = None
    api_key: Optional[str] = None
    recipient_mail: Optional[str] = None

class StartResponse(BaseResponse):
    data: Optional[Dict[str, str]] = None

# STOP
class StopRequest(BaseModel):
    gw_id: str
    force: Optional[bool] = None

class StopResponse(BaseResponse):
    data: Optional[Dict[str, str]] = None

# STATUS
class StatusResponse(BaseResponse):
    data: Optional[Dict[str, Any]] = None

# COMMAND
class CommandRequest(BaseModel):
    gw_id: str
    payload: Dict[str, Any]

class CommandResponse(BaseResponse):
    data: Optional[Dict[str, Any]] = None

# -----------------------
# Backend abstraction
# -----------------------
class MediaBackend(ABC):
    """Abstract gateway backend interface used by the API routes."""

    @abstractmethod
    def start_gateway(self, req: StartRequest) -> Dict[str, Any]:
        """Start a gateway instance. Returns a dict with processing_state and optional data."""
        pass

    @abstractmethod
    def stop_gateway(self, req: StopRequest) -> Dict[str, Any]:
        """Stop a gateway instance. Returns a dict with processing_state and optional data."""
        pass

    @abstractmethod
    def get_status(self, gw_id: str) -> Dict[str, Any]:
        """Return gateway status or raise ValueError if not found."""
        pass

    @abstractmethod
    def send_command(self, gw_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Send an arbitrary command to the gateway; return result or raise ValueError."""
        pass

# -----------------------
# DockerGateway (placeholder)
# -----------------------
class DockerGateway(MediaBackend):
    """
    Real implementation placeholder.
    NOTE: This class should contain the real docker/docker-compose logic in production.
    Here it returns deterministic placeholder responses so API routes stay decoupled.
    """

    def __init__(self):
        # In real impl: initialize docker client or CLI helpers
        self._store: Dict[str, Dict[str, Any]] = {}

    @staticmethod
    def get_status_by_name(entries, wanted_name):
        for e in entries:
            if e.get("Name") == wanted_name:
                return e.get("Status")
        return None

    @staticmethod
    def get_gateway_docker_status(gw_id: str) -> Dict[str, Any]:
        # Check docker compose status for the gateway
        gwSubProc = ['docker', 'compose', 'ls', '-a','--format', 'json']
        res = subprocess.Popen(gwSubProc, cwd='.', stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = res.communicate()
        decoded = out.decode('utf-8').strip()
        try:
            parsed = json.loads(decoded)
            if isinstance(parsed, dict):
                result = [parsed]
            elif isinstance(parsed, list):
                result = parsed
            else:
                raise ValueError("Unexpected format")
        except json.JSONDecodeError:
            result = [json.loads(line) for line in decoded.split('\n') if line.strip()]

        status = DockerGateway.get_status_by_name(result, gw_id)
        return status

    def start_gateway(self, req: StartRequest) -> Dict[str, Any]:
        print(f"[START CONTAINER] for gateway room={req.room} main_app={req.main_app}")
        gwSubProc = ['./SIPMediaGW.sh']
        gwSubProc.extend(['-r', req.room])
        #if req.fromId:
        #    gwSubProc.extend(['-f', req.fromId])
        if req.prefix:
            gwSubProc.extend(['-p', req.prefix])
        if req.webrtc_domain:
            gwSubProc.extend(['-w', req.webrtc_domain.model_dump_json()])
        if req.rtmp_dst:
            gwSubProc.extend(['-u', req.rtmp_dst])
        if req.dial:
            gwSubProc.extend(['-d', req.dial])
        if req.loop:
            gwSubProc.append('-l')
        if req.transcript == 'true':
            gwSubProc.append('-s')
        if req.audio_only == 'true':
            gwSubProc.append('-o')
        if req.api_key:
            gwSubProc.extend(['-k', req.api_key])
        if req.recipient_mail:
            gwSubProc.extend(['-m', req.recipient_mail])
        if req.gw_id:
            gwSubProc.extend(['-g', req.gw_id])
        if req.main_app:
            gwSubProc.extend(['-a', req.main_app])

        filePath = os.path.dirname(__file__)
        print(gwSubProc)
        res = subprocess.Popen(gwSubProc, cwd=filePath, stdout=subprocess.PIPE)
        res.wait()
        resStr = res.stdout.read().decode('utf-8')
        resJson = json.loads(resStr.replace("'", '"'))

        print(f"[CONTAINER STARTED] for gateway gwName={req.gw_id} room={req.room} main_app={req.main_app} result={resJson}")
       
        if resJson.get("res") != "ok":
            raise ValueError("Failed to start gateway container")
        
        return {"processing_state": "working", "gw_id": req.gw_id}

    def stop_gateway(self, req: StopRequest) -> Dict[str, Any]:
        print(f"[STOP CONTAINER] for gateway id={req.gw_id}")
        gwSubProc = ['docker', 'compose', 'ls','--format', 'json', '-q' ]
        res = subprocess.Popen(gwSubProc, cwd='.', stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        res.wait()
        resStr = res.stdout.read().decode('utf-8')
        projects=resStr.splitlines()
        projectName = req.gw_id
        if projectName in projects:
            gwSubProc = ['docker', 'compose']
            gwSubProc.extend(['-p', projectName])
        else:
            raise ValueError("no running container for gw_id={}".format(req.gw_id))

        if 'force' in req and req.force:
            gwSubProc.append('down')
        else:
            gwSubProc.append('stop')
            gwSubProc.append('gw')
        filePath = os.path.dirname(__file__)
        print(gwSubProc)
        res = subprocess.Popen(gwSubProc, cwd=filePath, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        res.wait()
        resStr = res.stderr.read().decode('utf-8')
        retStr = ''
        lines = resStr.splitlines()
        for line in lines:
            if 'level=warning' not in line:
                if retStr:
                    retStr += ' => '
                retStr += line
        resJson = {'status': 'success', 'res': retStr}
        print(f"[CONTAINER STOPPED] for gateway id={req.gw_id} result={resJson}")
     
        return {"processing_state": "stopped"}

    def get_status(self, gw_id: str) -> Dict[str, Any]:
        print(f"[STATUS] id={gw_id}")

        status = DockerGateway.get_gateway_docker_status(gw_id)

        if 'exited' in status:
            return {"gw_state": "down", "detail": "exited"}
        elif status is None:
            raise ValueError("Gateway not found")
        
        # Check docker compose ps for the gateway
        gwSubProc = ['docker', 'compose', '-p', gw_id, 'ps', '--format', 'json']
        res = subprocess.Popen(gwSubProc, cwd='.', stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = res.communicate()
        decoded = out.decode('utf-8').strip()
        try:
            parsed = json.loads(decoded)
            if isinstance(parsed, dict):
                result = [parsed]
            elif isinstance(parsed, list):
                result = parsed
            else:
                raise ValueError("Unexpected format")
        except json.JSONDecodeError:
            result = [json.loads(line) for line in decoded.split('\n') if line.strip()]

        resp = {}
        if not result:
            resp['gw_state'] = "down"
            return resp
        else:
            resp['gw_state'] = "up"
        
        resp["gw_id"] = gw_id

        gwData = next((c for c in result if c.get("Name", "").startswith("gw")), None)
        gwName = gwData['Name']
        # Recording progress
        gwSubProc = ['docker', 'exec', gwName,
                        'sh', '-c',
                        ('[ "$MAIN_APP" = "recording" ] && '
                        'pid=$(pgrep -o ffmpeg) && '
                        '[ -n "$pid" ] && '
                        'ps -p $pid -o etimes= | '
                        'awk \'{ sec=$1; h=int(sec/3600); m=int((sec%3600)/60); s=sec%60; '
                        'printf "%02d:%02d:%02d", h, m, s }\'')]
        res = subprocess.Popen(gwSubProc, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = res.communicate()
        recordElapsed = out.decode().strip()
        if recordElapsed:
            resp["recording_duration"] = recordElapsed
        gwSubProc = ['docker', 'exec', gwName, 'sh', '-c', 'echo $WITH_TRANSCRIPT']
        res = subprocess.Popen(gwSubProc, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        out, err = res.communicate()
        withTranscript = out.decode().strip()
        if withTranscript == 'true':
            # Transcript progress
            gwSubProc = ['docker', 'exec', gwName, 'sh', '-c', 'ls /var/recording/*.mp4']
            res = subprocess.Popen(gwSubProc, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            out, err = res.communicate()
            mp4List = out.decode().split()
            processedPercent = (
                f"{(sum(f.endswith('.processed.mp4') for f in mp4List) / len(mp4List) * 100):.0f}%"
                if mp4List else "0%"
            )
            resp["transcript_progress"] = processedPercent
        return resp

    def send_command(self, gw_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        print(f"[COMMAND] id={gw_id} payload={payload}")
        status = DockerGateway.get_gateway_docker_status(gw_id)
        if status is None:
            raise ValueError("Gateway not found")
        return {"ack": True, "received": payload}

# -----------------------
# FakeGateway (in-memory deterministic, for tests)
# -----------------------
class FakeGateway(MediaBackend):
    """In-memory fake backend suitable for unit/integration tests. Deterministic behaviour."""

    def __init__(self):
        # Simple in-memory map: gw_id -> metadata
        self._store: Dict[str, Dict[str, Any]] = {}

    def start_gateway(self, req: StartRequest) -> Dict[str, Any]:
        now = dt.datetime.utcnow().isoformat()
        self._store[req.gw_id] = {
            "gw_state": "up",
            "processing_state": "working",
            "gw_id": req.gw_id,
            "room": req.room,
            "start_time": now,
            "recording_duration": "00:00:00",
            "transcript_progress": "0%",
        }
        return {"processing_state": "working", "gw_id": req.gw_id}

    def stop_gateway(self, req: StopRequest) -> Dict[str, Any]:
        if req.gw_id not in self._store:
            raise ValueError("Gateway not found")
        entry = self._store[req.gw_id]
        entry["gw_state"] = "down"
        entry["processing_state"] = "stopped"
        # deterministic final durations
        entry["recording_duration"] = entry.get("recording_duration", "00:00:00")
        entry["transcript_progress"] = entry.get("transcript_progress", "0%")
        return {"processing_state": "stopped"}

    def get_status(self, gw_id: str) -> Dict[str, Any]:
        if gw_id not in self._store:
            raise ValueError("Gateway not found")
        entry = self._store[gw_id].copy()
        # update deterministic recording duration based on start_time
        if entry.get("start_time") and entry.get("processing_state") == "working":
            start = dt.datetime.fromisoformat(entry["start_time"])
            elapsed = dt.datetime.utcnow() - start
            entry["recording_duration"] = str(elapsed).split(".")[0]
        return entry

    def send_command(self, gw_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if gw_id not in self._store:
            raise ValueError("Gateway not found")
        if self._store[gw_id].get("processing_state") == "stopped":
            raise ValueError("Gateway is stopped")
        # For tests, echo back command with deterministic ack
        return {"ack": True, "received": payload}

# -----------------------
# Backend selector (single place)
# -----------------------
@lru_cache()
def get_backend() -> MediaBackend:
    """
    Decide which backend to use based on environment variable MODE.
    - MODE=fake => FakeGateway
    - otherwise => DockerGateway
    Cached so DI returns the same instance.
    """
    mode = os.getenv("MODE", "").lower()
    if mode == "fake":
        return FakeGateway()
    return DockerGateway()

# -----------------------
# Exception handlers
# -----------------------
@app.exception_handler(RequestValidationError)
def validation_exception_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "status": "error",
            "error": "Invalid input",
            "message": exc.errors(),
        },
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": "error",
            "error": {
                "code": exc.status_code,
                "detail": exc.detail
            },
            "data": None
        }
    )

# -----------------------
# HTTP Routes (no direct docker calls; backend injected)
# -----------------------
@app.post("/gateway/start", response_model=StartResponse)
def start_gateway(req: StartRequest, backend: MediaBackend = Depends(get_backend)):
    try:
        res = backend.start_gateway(req)
        return StartResponse(status="success", data={"processing_state": res.get("processing_state"), "gw_id": res.get("gw_id")})
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start gateway: {e}")

@app.post("/gateway/stop", response_model=StopResponse)
def stop(req: StopRequest, backend: MediaBackend = Depends(get_backend)):
    try:
        res = backend.stop_gateway(req)
        return StopResponse(status="success", data={"processing_state": res.get("processing_state")})
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stop gateway: {e}")

@app.get("/gateway/status", response_model=StatusResponse)
def status(gw_id: str, backend: MediaBackend = Depends(get_backend)):
    try:
        data = backend.get_status(gw_id)
        return StatusResponse(status="success", data=data)
    except ValueError as ve:
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/gateway/command", response_model=CommandResponse)
def command(req: CommandRequest, backend: MediaBackend = Depends(get_backend)):
    try:
        result = backend.send_command(req.gw_id, req.payload)
        return CommandResponse(status="success", data=result)
    except ValueError as ve:
        # 403 for stopped gateway, 404 for not found (backend decides)
        msg = str(ve).lower()
        if "stopped" in msg:
            raise HTTPException(status_code=403, detail=str(ve))
        raise HTTPException(status_code=404, detail=str(ve))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# -----------------------
# Entrypoint
# -----------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="HTTP Launcher for SIP Media Gateway")
    parser.add_argument("--port", type=int, default=8100, help="Port to run the HTTP server on")
    args = parser.parse_args()
    uvicorn.run(app, host="0.0.0.0", port=args.port)