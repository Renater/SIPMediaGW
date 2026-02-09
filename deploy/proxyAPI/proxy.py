import asyncio
import json
import re
import redis
import os
import httpx
import datetime as dt
import uvicorn
from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse

app = FastAPI()



redisClient = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)
allowedToken = "1234"
adminToken = "admin-secret-key"  # Change this to a secure admin key

# Redis Mapping:
# gateway:<gw_id> => "<gw_ip>|<state>|type|room_name|start_time|<media_duration>|<transcript_progress>"
# state: started | working | stopped

redis_gw_field_count = 7

redis_gw_ip_index = 0
redis_gw_state_index = 1
redis_gw_type_index = 2
redis_gw_room_index = 3
redis_gw_start_time_index = 4
redis_gw_media_duration_index = 5
redis_gw_transcript_progress_index = 6


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

def authorize(request: Request):
    authHeader = request.headers.get("Authorization")
    if not authHeader or not re.match(r"^Bearer ", authHeader):
        return False
    token = authHeader.split(" ", 1)[1]
    return token == allowedToken

def authorizeAdmin(request: Request):
    """Check if request has valid admin token"""
    authHeader = request.headers.get("Authorization")
    if not authHeader or not re.match(r"^Bearer ", authHeader):
        return False
    token = authHeader.split(" ", 1)[1]
    return token == adminToken

def findAvailableGateway():
    for key in redisClient.scan_iter(match="gateway:*"):
        value = redisClient.get(key)
        parts = value.split("|")
        gwIp = parts[redis_gw_ip_index]
        state = parts[redis_gw_state_index] if len(parts) > redis_gw_state_index else None
        if state == "started":
            return [key, gwIp]
    return None

def updateProgressInfo(gw_id: str, parts: list, data: dict):
    recording = data.get("recording_duration")
    streaming = data.get("streaming_duration")
    transcript = data.get("transcript_progress")
    state  = data.get("gw_state")
    parts += [""] * (redis_gw_field_count - len(parts))
    if recording:
        parts[redis_gw_media_duration_index] = f"{recording}"
    if streaming:
        parts[redis_gw_media_duration_index] = f"{streaming}"
    if transcript:
        parts[redis_gw_transcript_progress_index] = f"{transcript}"
    # Update Gateway State
    if (state == "up"):
        parts[redis_gw_state_index] = "working"
    elif (state == "down"):
        parts[redis_gw_state_index] = "started"

    mapping = "|".join(parts)
    redisClient.set(f"gateway:{gw_id}", mapping)

def getGatewayStatusFromRedis(gw_id: str):
    rawValue = redisClient.get(f"gateway:{gw_id}")
    if not rawValue:
        return None
    parts = rawValue.split("|")
    gwIp = parts[redis_gw_ip_index]
    room = parts[redis_gw_room_index] if len(parts) > redis_gw_room_index else None
    state = parts[redis_gw_state_index] if len(parts) > redis_gw_state_index else None
    media_duration = parts[redis_gw_media_duration_index] if len(parts) > redis_gw_media_duration_index else None
    redis_gw_transcript_progress_index = 6
    transcript = parts[redis_gw_transcript_progress_index] if len(parts) > redis_gw_transcript_progress_index else None
    return {
        "status": "success",
        "data": {
            "gw_id": gw_id,
            "gw_state": state,
            "room": room,
            "media_duration": media_duration,
            "transcript_progress": transcript
        }
    }

@app.get("/admin/statuses")
async def adminStatus(request: Request):
    """GET /admin/statuses - Get status of all gateways (admin only)"""
    if not authorizeAdmin(request):
        return Response(
            json.dumps({"error": "authorization error"}),
            status_code=401,
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
            media_type="application/json"
        )
    
    result = {}
    for key in redisClient.scan_iter(match="gateway:*"):
        gw_id = key.split(":")[-1]
        raw = redisClient.get(key)
        if not raw:
            continue
        parts = raw.split("|")
        gwIp = parts[redis_gw_ip_index]
        room = parts[redis_gw_room_index] if len(parts) > redis_gw_room_index else None
        state = parts[redis_gw_state_index] if len(parts) > redis_gw_state_index else None
        media_duration = parts[redis_gw_media_duration_index] if len(parts) > redis_gw_media_duration_index else None
        transcript = parts[redis_gw_transcript_progress_index] if len(parts) > redis_gw_transcript_progress_index else None

        result[gw_id] = {
            "gateway": gwIp,
            "status": state,
            "room": room,
            "media_duration": media_duration,
            "transcript_progress": transcript
        }
    return result

# Background task to monitor gateways
async def monitorGateways(intervalSeconds: int = 30):
    """Periodically check gateway states and update Redis mappings"""
    while True:
        print("Checking gateway states...")
        for key in redisClient.scan_iter(match="gateway:*"):
            gw_id = key.split(":")[-1]
            value = redisClient.get(key)
            if not value:
                continue

            parts = value.split("|")
            gwIp = parts[redis_gw_ip_index]

            url = f"http://{gwIp}/gateway/status"
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    headers = {"Authorization": f"Bearer {allowedToken}"}
                    response = await client.get(url, params={"gw_id": gw_id}, headers=headers)

                    data = response.json()
                    if data.get("status") == "success":
                        updateProgressInfo(gw_id, parts, data.get("data"))
                    elif data.get("status") == "error":
                        print(f"Gateway {gw_id} doesn't exist, removing mapping")
                        redisClient.delete(key)
                    
            except Exception as e:
                print(f"Error checking {gwIp}: {e}")                
                print(f"Removing mapping for Gateway {gw_id} (Http GW API is down)")
                redisClient.delete(key)

        await asyncio.sleep(intervalSeconds)

@app.on_event("startup")
async def startupEvent():
    asyncio.create_task(monitorGateways(intervalSeconds=30))

@app.get("/assets/{file_name}")
def get_asset(file_name: str):
    if file_name != "assets.tar.xz":
        raise HTTPException(status_code=404, detail="Fichier non trouvé.")
    file_path = "./assets/assets.tar.xz"
    if not os.path.isfile(file_path):
        raise HTTPException(status_code=404, detail="Fichier non trouvé.")
    return FileResponse(
        path=file_path,
        media_type="application/x-xz",
        filename=file_name,
    )

async def proxyToGateway(gwUrl: str, request: Request, params: dict, body: dict,headers: dict):
    """Forward request to gateway and return response"""
    try:
        async with httpx.AsyncClient(timeout=None) as client:
            if request.method == "GET":
                gwResponse = await client.get(gwUrl, params=params, headers=headers)
            else:
                gwResponse = await client.request(
                    request.method,
                    gwUrl,
                    params=params,
                    json=body,
                    headers=headers
                )
        return gwResponse
    except httpx.ReadTimeout:
        raise HTTPException(status_code=504, detail="Gateway timeout")

@app.post("/start")
async def startGateway(request: Request):
    """POST /start - Start gateway for a room"""
    if not authorize(request):
        return Response(
            json.dumps({"error": "authorization error"}),
            status_code=401,
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
            media_type="application/json"
        )
    
    room = (await request.json()).get("room")
    if not room:
        raise HTTPException(status_code=400, detail="Missing 'room' parameter")

    main_app = (await request.json()).get("main_app")
    if not main_app:
        raise HTTPException(status_code=400, detail="Missing 'main_app' parameter")

    gateway = findAvailableGateway()
    if not gateway:
        raise HTTPException(status_code=503, detail="No available gateways")
    
    gw_id = gateway[0].split(":")[-1]
    gwIp = gateway[1]
    
    print(f"Allocating gateway {gw_id} ({gwIp}) for room {room}")
    
    params = dict(request.query_params)
    
    gwUrl = f"http://{gwIp}/gateway/start"
    headers = {"Authorization": request.headers.get("Authorization", "")}
    body = await request.json()
    body["gw_id"]= gw_id

    gwResponse = await proxyToGateway(gwUrl, request, params, body, headers)
    responseJson = gwResponse.json()
    
    try:
        status = responseJson.get("status")
        if status == "success":
            # Mark as working
            rawValue = redisClient.get(f"gateway:{gw_id}")
            parts = rawValue.split("|") if rawValue else [gwIp]
            parts += [""] * (redis_gw_field_count - len(parts))
            parts[redis_gw_state_index] = "working"
            parts[redis_gw_room_index] = room
            mapping = "|".join(parts)
            redisClient.set(f"gateway:{gw_id}", mapping)
        else:
            raise HTTPException(status_code=503, detail=responseJson.get("error").get("detail"))
    except Exception as e:
        raise HTTPException(status_code=503, detail="Faild to parse Gateway Json response")
    
    return Response(
        content=json.dumps(responseJson),
        status_code=gwResponse.status_code,
        media_type="application/json"
    )

@app.post("/stop")
async def stopGateway(request: Request):
    """POST /stop - Stop gateway"""
    if not authorize(request):
        return Response(
            json.dumps({"error": "authorization error"}),
            status_code=401,
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
            media_type="application/json"
        )

    gw_id = (await request.json()).get("gw_id")
    if not gw_id:
        raise HTTPException(status_code=400, detail="Missing 'gw_id' parameter")
    
    rawValue = redisClient.get(f"gateway:{gw_id}")
    if not rawValue:
        raise HTTPException(status_code=404, detail=f"No mapping found for gateway '{gw_id}'")
    
    parts = rawValue.split("|")
    gwIp = parts[redis_gw_ip_index]
    body = await request.json()

    params = dict(request.query_params)
    gwUrl = f"http://{gwIp}/gateway/stop"
    headers = {"Authorization": request.headers.get("Authorization", "")}
    
    gwResponse = await proxyToGateway(gwUrl, request, params, body, headers)
    responseJson = gwResponse.json()
    print("Gateway Stop Response:", responseJson)
    
    try:
        detailsRes = responseJson.get("data", {}).get("processing_state", "")
        if "stopping" in detailsRes or "stopped" in detailsRes:
            # Mark as stopped
            parts[redis_gw_room_index] = "None"
            parts[redis_gw_state_index] = "stopped"
            mapping = "|".join(parts)
            redisClient.set(f"gateway:{gw_id}", mapping)
            responseJson["status"] = "success"
        else:
            responseJson["status"] = "error"
    except Exception as e:
        print("Failed to parse JSON response:", e)
        responseJson["status"] = "error"
    
    return Response(
        content=json.dumps(responseJson),
        status_code=gwResponse.status_code,
        media_type="application/json"
    )

@app.get("/status")
@app.get("/progress")
async def statusGateway(request: Request, gw_id: str = None, room: str = None):
    """GET /status?gw_id=gatewayName - Get gateway status"""
    if not authorize(request):
        return Response(
            json.dumps({"error": "authorization error"}),
            status_code=401,
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
            media_type="application/json"
        )



    if not gw_id and not room:
        raise HTTPException(status_code=400, detail="Missing 'gw_id' or 'room' parameter")

    if room:
        # Find gateway by room
        gw_id = None
        for key in redisClient.scan_iter(match="gateway:*"):
            rawValue = redisClient.get(key)
            if not rawValue:
                continue
            parts = rawValue.split("|")
            gwRoom = parts[redis_gw_room_index] if len(parts) > redis_gw_room_index else None
            if gwRoom == room:
                gw_id = key.split(":")[-1]
                break
        if not gw_id:
            raise HTTPException(status_code=404, detail=f"No gateway found for room '{room}'")

    rawValue = redisClient.get(f"gateway:{gw_id}")
    if not rawValue:
        raise HTTPException(status_code=404, detail=f"Gateway '{gw_id}' not found")
    
    parts = rawValue.split("|")
    gwIp = parts[redis_gw_ip_index]

    
    # Get Status from Redis
    responseJson = getGatewayStatusFromRedis(gw_id)
    if responseJson:
        return Response(
            content=json.dumps(responseJson),
            status_code=200,
            media_type="application/json"
        )
    else:
        return Response(
            content=json.dumps({"status": "error", "error": "Failed to get gateway status", "data": None}),
            status_code=404,
            media_type="application/json"
        )

@app.api_route("/command", methods=["GET", "POST"])
async def commandGateway(request: Request):
    """GET/POST /command - Send command to gateway"""
    if not authorize(request):
        return Response(
            json.dumps({"error": "authorization error"}),
            status_code=401,
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
            media_type="application/json"
        )

    body = await request.json()
    gw_id = body.get("gw_id")

    if not gw_id:
        raise HTTPException(status_code=400, detail="Missing 'gw_id' parameter")
    
    rawValue = redisClient.get(f"gateway:{gw_id}")
    if not rawValue:
        raise HTTPException(status_code=404, detail=f"Gateway '{gw_id}' not found")
    
    parts = rawValue.split("|")
    gwIp = parts[redis_gw_ip_index]
    isStopped = len(parts) > redis_gw_state_index and parts[redis_gw_state_index] != "working"

    if isStopped:
        raise HTTPException(status_code=403, detail=f"Gateway '{gw_id}' is stopped, cannot send commands")
    body = await request.json()

    params = dict(request.query_params)
    gwUrl = f"http://{gwIp}/command"
    headers = {"Authorization": request.headers.get("Authorization", "")}
    
    gwResponse = await proxyToGateway(gwUrl, request, params, body, headers)
    responseJson = gwResponse.json()
    
    return Response(
        content=json.dumps(responseJson),
        status_code=gwResponse.status_code,
        media_type="application/json"
    )

@app.post("/register")
async def registerGateway(request: Request):
    """POST /register - Register a new gateway"""
    if not authorize(request):
        return Response(
            json.dumps({"error": "authorization error"}),
            status_code=401,
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
            media_type="application/json"
        )
    
    try:
        body = await request.json()
        gwIp = body.get("gw_ip")
        gw_id = body.get("gw_id")
        gwType = body.get("gw_type", "media")
        
        if not gwIp or not gw_id:
            raise HTTPException(status_code=400, detail="Missing 'gwIp' or 'gw_id'")
        
        # Register gateway in Redis
        startTime = dt.datetime.now().isoformat()
        gwValue = f"{gwIp}|started|{gwType}|None|{startTime}|0|0"
        redisClient.set(f"gateway:{gw_id}", gwValue)
        
        print(f"Gateway registered: {gw_id} ({gwIp})")
        
        return Response(
            content=json.dumps({"status": "success", "gw_id": gw_id, "gw_ip": gwIp}),
            status_code=200,
            media_type="application/json"
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/unregister")
async def unregisterGateway(request: Request):
    """POST /unregister - Unregister a gateway"""
    if not authorize(request):
        return Response(
            json.dumps({"error": "authorization error"}),
            status_code=401,
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
            media_type="application/json"
        )
    
    try:
        body = await request.json()
        gw_id = body.get("gw_id")
        
        if not gw_id:
            raise HTTPException(status_code=400, detail="Missing 'gw_id'")
        
        # Check if gateway exists
        if not redisClient.exists(f"gateway:{gw_id}"):
            raise HTTPException(status_code=404, detail=f"Gateway '{gw_id}' not found")
        
        # Remove gateway from Redis
        redisClient.delete(f"gateway:{gw_id}")
        
        print(f"Gateway unregistered: {gw_id}")
        
        return Response(
            content=json.dumps({"status": "success", "gw_id": gw_id, "removed": True}),
            status_code=200,
            media_type="application/json"
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=9000)