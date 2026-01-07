from fastapi import FastAPI
from pydantic import BaseModel, RootModel,field_validator
from typing import Optional, Dict, Any
import uuid
import redis
import datetime as dt
import os
import subprocess
import json
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

app = FastAPI(title="SIP Media Gateway API", version="1.0.0")

use_container = True

# -----------------------
# 📌 Modèles
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
    webrtc_domain: WebRTCDomain
    gw_id: str
    fromId: Optional[str] = None
    prefix: Optional[str] = None
    rtmpDst: Optional[str] = None
    dial: Optional[str] = None
    loop: Optional[bool] = None
    transcript: Optional[str] = None
    audioOnly: Optional[str] = None
    apiKey: Optional[str] = None
    recipientMail: Optional[str] = None

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

# models for add/remove gateway VM
class AddGatewayRequest(BaseModel):
    gwIp: str
    gwType: Optional[str] = "media"

class AddGatewayResponse(BaseResponse):
    data: Optional[Dict[str, str]] = None

class RemoveGatewayRequest(BaseModel):
    gw_id: str

class RemoveGatewayResponse(BaseResponse):
    data: Optional[Dict[str, Any]] = None

# -----------------------
# 📡 Logique "launcher"
# (à remplacer par ton vrai code GW)
# -----------------------

def start_gateway_container(req: StartRequest) -> Dict[str, Any]:
    print(f"[START CONTAINER] for gateway room={req.room}")
    gwSubProc = ['./SIPMediaGW.sh']
    gwSubProc.extend(['-r', req.room])
    if 'fromId' in req:
        gwSubProc.extend(['-f', req.fromId])
    if 'prefix' in req:
        gwSubProc.extend(['-p', req.prefix])
    if 'domain' in req:
        gwSubProc.extend(['-w', req.domain])
    if 'rtmpDst' in req:
        gwSubProc.extend(['-u', req.rtmpDst])
    if 'dial' in req:
        gwSubProc.extend(['-d', req.dial])
    if 'loop' in req and req.loop:
        gwSubProc.append('-l')
    if 'transcript' in req and req.transcript == 'true':
        gwSubProc.append('-s')
    if 'audioOnly' in req and req.audioOnly == 'true':
        gwSubProc.append('-o')
    if 'apiKey' in req:
        gwSubProc.extend(['-k', req.apiKey])
    if 'recipientMail' in req:
        gwSubProc.extend(['-m', req.recipientMail])
    if 'gw_id' in req:
        gwSubProc.extend(['-g', req.gw_id])
    
    filePath = os.path.dirname(__file__)
    print(gwSubProc)
    res = subprocess.Popen(gwSubProc, cwd=filePath, stdout=subprocess.PIPE)
    res.wait()
    resStr = res.stdout.read().decode('utf-8')
    resJson = json.loads(resStr.replace("'", '"'))

    print(f"[CONTAINER STARTED] for gateway gwName={req.gw_id} room={req.room} result={resJson}")
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
        return json.dumps({"status": "error", "message": "no running container for room={}".format(req.gw_id)})

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
    print(f"[LAUNCH] type={req.type} room={req.room} webrtc_domain={req.webrtc_domain} gw_id={req.gw_id}")
    
    if use_container:
        print(f"[LAUNCH] Gateway container")
        result = start_gateway_container(req)
        if result.get("status") != "success":
            raise ValueError("Failed to start gateway container")

    # Set Gateway state to "working"
    value = redisClient.get(req.gw_id)
    parts = value.split("|")
    gwIp = parts[0]
    state = parts[1] if len(parts) > 1 else None
    if state == "started":
        redisClient.set(req.gw_id, f"{gwIp}|working|{parts[2]}|{parts[3]}|{dt.datetime.now().isoformat()}")
        return "working"
    else:
        return "no available gateway found"

def stop_gateway(req: StopRequest) -> str:
    print(f"[STOP] id={req.gw_id}")
    if use_container:
        print(f"[STOP] Gateway container stop")
        result = stop_gateway_container(req)
        if result.get("status") != "success":
            raise ValueError(f"Failed to stop gateway container for id={req.gw_id}")

    # Set Gateway state to "stopped"
    value = redisClient.get(req.gw_id)
    parts = value.split("|")
    if len(parts) > 1:
        redisClient.set(req.gw_id, f"{parts[0]}|stopped|{parts[2]}|{parts[3]}|{dt.datetime.now().isoformat()}")
    return "stopped"

def get_gateway_status(gw_id: str) -> Dict[str, Any]:
    print(f"[STATUS] id={gw_id}")
    # TODO: return real status
    return {
        "task": "recording",
        "record_time": 178,
        "transcript_progress": 0.61,
    }

def send_gateway_command(gw_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    print(f"[COMMAND] id={gw_id} payload={payload}")
    return {"ack": True, "received": payload}

def add_gateway_resource(gw_ip: str, gw_type: str) -> str:
    global nbGw
    print(f"[ADD GW] ip={gw_ip} type={gw_type}")
    gw_id = f"{gw_ip}-gw{nbGw}"
    nbGw += 1
    gwType = gw_type or "media"
    startTime = dt.datetime.now().isoformat()
    statusUpdateTime = startTime
    gwValue = f"{gw_ip}|started|{gwType}|{startTime}|{statusUpdateTime}"
    redisClient.set(f"gateway:{gw_id}", gwValue)
    return gw_id

def remove_gateway_resource(gw_id: str) -> bool:
    global nbGw
    print(f"[REMOVE GW] id={gw_id}")
    deleted = redisClient.delete(f"{gw_id}")
    if deleted:
        nbGw = max(0, nbGw - 1)
        return True
    return False

# -----------------------
# 🛠️ Redis / state for VM management (fake)
# -----------------------
redisClient = redis.Redis(host='127.0.0.1', port=6379, db=0, decode_responses=True)
nbGw = 0

# -----------------------
# 🛣️ Routes HTTP
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


@app.post("/gateway/start", response_model=StartResponse)
def start_gateway(req: StartRequest):
    try:
        state = launch_gateway(req)
        if state == "no available gateway found":
            raise ValueError("No available gateway found")
        return StartResponse(status="success", data={"processing_state": state})
    except Exception as e:
        return StartResponse(status="error", error={"code": "GW_START_ERROR", "message": str(e)})


@app.post("/gateway/stop", response_model=StopResponse)
def stop(req: StopRequest):
    try:
        state = stop_gateway(req)
        return StopResponse(status="success", data={"processing_state": state})
    except Exception as e:
        return StopResponse(status="error", error={"code": "GW_STOP_ERROR", "message": str(e)})


@app.get("/gateway/{id}/status", response_model=StatusResponse)
def status(id: str):
    try:
        data = get_gateway_status(id)
        return StatusResponse(status="success", data=data)
    except Exception as e:
        return StatusResponse(status="error", error={"code": "GW_STATUS_ERROR", "message": str(e)})


@app.post("/gateway/{id}/command", response_model=CommandResponse)
def command(id: str, req: CommandRequest):
    try:
        result = send_gateway_command(id, req.root)
        return CommandResponse(status="success", data=result)
    except Exception as e:
        return CommandResponse(status="error", error={"code": "GW_COMMAND_ERROR", "message": str(e)})


@app.post("/gateway/add_gw", response_model=AddGatewayResponse)
def add_gateway(req: AddGatewayRequest):
    try:
        result = add_gateway_resource(req.gwIp, req.gwType)
        return AddGatewayResponse(status="success", data={"gw_id": result})
    except Exception as e:
        return AddGatewayResponse(status="error", error={"code": "ADD_GW_ERROR", "message": str(e)})


@app.post("/gateway/remove_gw", response_model=RemoveGatewayResponse)
def remove_gateway(req: RemoveGatewayRequest):
    try:
        result = remove_gateway_resource(req.gw_id)
        return RemoveGatewayResponse(status="success", data={"removed": result})
    except Exception as e:
        return RemoveGatewayResponse(status="error", error={"code": "REMOVE_GW_ERROR", "message": str(e)})
    
