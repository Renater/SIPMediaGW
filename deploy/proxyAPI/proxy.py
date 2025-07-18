import asyncio
import json
import re
import redis
import os
import httpx
from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.responses import FileResponse

app = FastAPI()

redisClient = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)
allowedToken = "1234"

gateways = ["127.0.0.1"]  # List of available gateways IP addresses

def authorize(request: Request):
    authHeader = request.headers.get("Authorization")
    if not authHeader or not re.match(r"^Bearer ", authHeader):
        return False
    token = authHeader.split(" ", 1)[1]
    return token == allowedToken

def findAvailableGateway():
    assignedGateways = {
        value.split("|")[0]
        for value in redisClient.mget(redisClient.scan_iter(match="room:*"))
        if value
    }
    for gw in gateways:
        if gw not in assignedGateways:
            return gw
    return None

def updateProgressInfo(room: str, parts: list, data: dict):
    recording = data.get("recording_duration")
    transcript = data.get("transcript_progress")
    parts += [""] * (4 - len(parts))
    if recording:
        parts[2] = f"{recording}"
    if transcript:
        parts[3] = f"{transcript}"
    mapping = "|".join(parts)
    redisClient.set(f"room:{room}", mapping)

@app.get("/status")
async def status():
    result = {}
    for key in redisClient.scan_iter(match="room:*"):
        room = key.split("room:")[1]
        raw = redisClient.get(key)
        if not raw:
            continue
        parts = raw.split("|")
        gwIp = parts[0]
        state = parts[1] if len(parts) > 1 else None
        recording = parts[2] if len(parts) > 2 else None
        transcript = parts[3] if len(parts) > 3 else None

        result[room] = {
            "gateway": gwIp,
            "status": state,
            "recording_duration": recording,
            "transcript_progress": transcript
        }
    return result

@app.api_route("/{action}", methods=["GET", "POST"])
async def proxyRequest(action: str, request: Request):
    if not authorize(request):
        return Response(
            json.dumps({"error": "authorization error"}),
            status_code=401,
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
            media_type="application/json"
        )

    room = request.query_params.get("room")
    if not room:
        raise HTTPException(status_code=400, detail="Missing 'room' parameter")

    rawValue = redisClient.get(f"room:{room}")
    gwIp = None
    isStopped = False

    if rawValue:
        parts = rawValue.split("|")
        gwIp = parts[0]
        isStopped = len(parts) > 1 and parts[1] == "stopped"

    if not gwIp:
        if action == "start":
            gwIp = findAvailableGateway()
            if not gwIp:
                raise HTTPException(status_code=503, detail="No available gateways")
        else:
            raise HTTPException(status_code=404, detail=f"No mapping found for room '{room}'")

    if isStopped and action != "progress":
        raise HTTPException(status_code=403, detail=f"Room '{room}' is in a stopped state, only 'progress' allowed.")

    gwUrl = f"http://{gwIp}/{action}"
    headers = {
        "Authorization": request.headers.get("Authorization", "")
    }

    try:
        async with httpx.AsyncClient(timeout=None) as client:
            if request.method == "GET":
                gwResponse = await client.get(gwUrl, params=request.query_params, headers=headers)
            else:
                body = await request.body()
                gwResponse = await client.request(
                    request.method,
                    gwUrl,
                    params=request.query_params,
                    content=body,
                    headers=headers
                )
    except httpx.ReadTimeout:
        raise HTTPException(status_code=504, detail="Gateway timeout")

    if action == "start":
        if "No free resources found" not in gwResponse.text:
            redisClient.set(f"room:{room}", f"{gwIp}|started")

    elif action == "stop":
        try:
            responseJson = gwResponse.json()
            detailsRes = responseJson.get("details", {}).get("res", "")
            if "Stopping" in detailsRes and "Stopped" in detailsRes:
                # Mark as stopped (instead of deleting)
                parts[1]='stopped'
                mapping = "|".join(parts)
                redisClient.set(f"room:{room}", mapping)
        except Exception as e:
            print("Failed to parse JSON response:", e)

    return Response(
        content=gwResponse.content,
        status_code=gwResponse.status_code,
        headers={"Content-Type": gwResponse.headers.get("Content-Type", "application/json")}
    )

# Background task to monitor gateways
async def monitorGateways(intervalSeconds: int = 60):
    while True:
        print("Checking gateway states...")
        for key in redisClient.scan_iter(match="room:*"):
            room = key.split("room:")[1]
            value = redisClient.get(key)
            if not value:
                continue

            parts = value.split("|")
            gwIp = parts[0]
            isStopped = len(parts) > 1 and parts[1] == "stopped"

            url = f"http://{gwIp}/progress"
            try:
                async with httpx.AsyncClient(timeout=10.0) as client:
                    headers = {"Authorization": f"Bearer {allowedToken}"}
                    response = await client.get(url, params={"room": room}, headers=headers)
                    data = response.json()
                    if data.get("gw_state") == "down" and isStopped:
                        print(f"Removing mapping for room {room} (stopped + gw down)")
                        redisClient.delete(key)
                    else:
                        updateProgressInfo(room, parts, data)
            except Exception as e:
                print(f"Error checking {gwIp}: {e}")

        await asyncio.sleep(intervalSeconds)

@app.on_event("startup")
async def startupEvent():
    asyncio.create_task(monitorGateways(intervalSeconds=60))

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
