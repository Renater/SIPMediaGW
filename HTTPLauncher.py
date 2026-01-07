from fastapi import FastAPI
from pydantic import BaseModel, RootModel,field_validator
from typing import Optional, Dict, Any
import redis
import datetime as dt
import os
import subprocess
import json
import uvicorn
import argparse

from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError, HTTPException

app = FastAPI(title="SIP Media Gateway API", version="1.0.0")

use_container = True

# -----------------------
# Modèles
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
    type: str               # Record / Streaming / SIP
    room: str
    gw_id: str
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
    main_app: Optional[str] = None
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
class CommandRequest(RootModel[Dict[str, Any]]):
    pass

class CommandResponse(BaseResponse):
    data: Optional[Dict[str, Any]] = None

# -----------------------
#  Logique "launcher"
# -----------------------

def start_gateway_container(req: StartRequest) -> Dict[str, Any]:
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
    return resJson

def stop_gateway_container(req: StopRequest) -> Dict[str, Any]:
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
    return resJson

def launch_gateway(req: StartRequest) -> str:
    print(f"[LAUNCH] type={req.type} room={req.room} webrtc_domain={req.webrtc_domain} gw_id={req.gw_id} main_app={req.main_app}")

    if use_container:

        status = get_gateway_docker_status(req.gw_id)
        if status is None:
            raise ValueError("Gateway not found")
        
        print(f"[LAUNCH] Gateway container")
        result = start_gateway_container(req)
        print(result)
        if result.get("res") != "ok":
            raise ValueError("Failed to start gateway container")

    return "working"

def stop_gateway(req: StopRequest) -> str:
    print(f"[STOP] id={req.gw_id}")
    if use_container:
        print(f"[STOP] Gateway container stop")
        status = get_gateway_docker_status(req.gw_id)
        if status is None:
            raise ValueError("Gateway not found")
        result = stop_gateway_container(req)
        if result.get("status") != "success":
            raise ValueError(f"Failed to stop gateway container for id={req.gw_id}")
    return "stopped"

def get_status_by_name(entries, wanted_name):
    for e in entries:
        if e.get("Name") == wanted_name:
            return e.get("Status")
    return None

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

    status = get_status_by_name(result, gw_id)
    return status

def get_gateway_status(gw_id: str) -> Dict[str, Any]:
    print(f"[STATUS] id={gw_id}")

    status = get_gateway_docker_status(gw_id)

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
 
def send_gateway_command(gw_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    print(f"[COMMAND] id={gw_id} payload={payload}")
    status = get_gateway_docker_status(gw_id)
    if status is None:
        raise ValueError("Gateway not found")
    return {"ack": True, "received": payload}

# -----------------------
# Redis / state for VM management (fake)
# -----------------------
nbGw = 0

# -----------------------
# Routes HTTP
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

@app.post("/gateway/start", response_model=StartResponse)
def start_gateway(req: StartRequest):
    try:
        state = launch_gateway(req)
        if state == "no available gateway found":
            raise ValueError("No available gateway found")
        return StartResponse(status="success", data={"processing_state": state,"gw_id":req.gw_id})
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to start gateway: {}".format(e))



@app.post("/gateway/stop", response_model=StopResponse)
def stop(req: StopRequest):
    try:
        state = stop_gateway(req)
        return StopResponse(status="success", data={"processing_state": state})
    except Exception as e:
        raise HTTPException(status_code=500, detail="Failed to stop gateway: {}".format(e))

@app.get("/gateway/status", response_model=StatusResponse)
def status(gw_id: str):
    try:
        data = get_gateway_status(gw_id)
        return StatusResponse(status="success", data=data)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.post("/gateway/command", response_model=CommandResponse)
def command(gw_id: str, req: CommandRequest):
    try:
        result = send_gateway_command(gw_id, req.root)
        return CommandResponse(status="success", data=result)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

if __name__ == "__main__":
    # get port from command line argument
    parser = argparse.ArgumentParser(description="HTTP Launcher for SIP Media Gateway")
    parser.add_argument("--port", type=int, default=8100, help="Port to run the HTTP server on")
    args = parser.parse_args()
    uvicorn.run(app, host="0.0.0.0", port=args.port)