import asyncio
import json
import re
import base64
import redis
import os
import httpx
import datetime as dt
import random, string
import uvicorn
from fastapi import FastAPI, Request, HTTPException, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.responses import RedirectResponse
from urllib.parse import quote_plus

app = FastAPI()

redisClient = redis.Redis(host=os.getenv('REDIS_HOST', '127.0.0.1'),
                          port=int(os.getenv('REDIS_PORT', '6379')),
                          decode_responses=True)

allowedToken = os.getenv("PROXY_TOKEN", "1234")
# No default: an unset PROXY_ADMIN_TOKEN disables admin routes (same
# convention as PROXY_ROOM_TOKEN) instead of exposing a well-known secret.
adminToken = os.getenv("PROXY_ADMIN_TOKEN", "")
# Dedicated token for room-side clients, which only need to resolve their own
# gateway id. Empty by default, which keeps /gateway_id closed: the route is
# only enabled on deployments where endpoints can be trusted to hold a secret.
roomToken = os.getenv("PROXY_ROOM_TOKEN", "")

# Redis Mapping:
# gateway:<gw_id> => "<gw_ip>|<state>|type|room_name|start_time|<media_duration>|<transcript_progress>|<browsing>|<peer_uri>|<peer_name>|<call_started>"
# state: started | working | stopped

redis_gw_field_count = 11

redis_gw_ip_index = 0
redis_gw_state_index = 1
redis_gw_type_index = 2
redis_gw_room_index = 3
redis_gw_start_time_index = 4
redis_gw_media_duration_index = 5
redis_gw_transcript_progress_index = 6
redis_gw_browsing_index = 7
redis_gw_peer_uri_index = 8
redis_gw_peer_name_index = 9
redis_gw_call_started_index = 10


def getPart(parts: list, index: int):
    """Safely read a mapping field, tolerating entries written before new
    fields were appended."""
    return parts[index] if len(parts) > index else None


def cleanPart(value):
    """Normalise a mapping field: empty and 'None' are returned as None."""
    return value if value and value != "" and value != "None" else None


@app.get("/pairing")
async def pairing_page(request: Request):
    """
    Serve the pairing HTML page so /pairing?error=...&pairingCode=...
    works and pairing.html.handleQueryParams() can show the message / prefill.
    """
    try:
        with open("pairing.html", "r", encoding="utf-8") as f:
            return Response(content=f.read(), media_type="text/html")
    except FileNotFoundError:
        return JSONResponse(status_code=404, content={"detail": "pairing.html not found"})

def adminUnauthorized():
    """401 for admin pages: Basic challenge so a browser prompts natively."""
    return Response(
        json.dumps({"error": "authorization error"}),
        status_code=401,
        headers={"WWW-Authenticate": 'Basic realm="SIPMediaGW admin", Bearer error="invalid_token"'},
        media_type="application/json"
    )

adminStaticFiles = {"admin.css": "text/css", "admin.js": "application/javascript",
                    "favicon.svg": "image/svg+xml"}

@app.get("/admin/")
async def admin_page(request: Request):
    """
    Serve the admin console. Same credentials as /admin/statuses: the browser
    re-sends them on the page's own calls. CSS and JS are external files so
    the page can carry a strict Content-Security-Policy (no inline code).
    """
    if not authorizeAdmin(request):
        return adminUnauthorized()
    try:
        with open("admin.html", "r", encoding="utf-8") as f:
            return Response(
                content=f.read(),
                media_type="text/html",
                headers={"Content-Security-Policy": "default-src 'self'; frame-ancestors 'none'"}
            )
    except FileNotFoundError:
        return JSONResponse(status_code=404, content={"detail": "admin.html not found"})

@app.get("/admin/static/{file_name}")
async def admin_static(request: Request, file_name: str):
    """Serve the console's CSS/JS (whitelist, no directory access)."""
    if not authorizeAdmin(request):
        return adminUnauthorized()
    mediaType = adminStaticFiles.get(file_name)
    if not mediaType:
        return JSONResponse(status_code=404, content={"detail": "not found"})
    try:
        with open(file_name, "r", encoding="utf-8") as f:
            return Response(content=f.read(), media_type=mediaType)
    except FileNotFoundError:
        return JSONResponse(status_code=404, content={"detail": f"{file_name} not found"})

# Connector icons (deploy/proxyAPI/icons, same set as the IVR's domain-icons),
# kept inside deploy/proxyAPI so the proxy stays a self-contained deployment unit.
adminIconsDir = os.getenv("ADMIN_ICONS_DIR", "icons")

@app.get("/admin/icons/{name}")
async def admin_icon(request: Request, name: str):
    """Serve a connector icon (<name>.png) from the mounted icons directory."""
    if not authorizeAdmin(request):
        return adminUnauthorized()
    if not re.fullmatch(r"[a-z0-9]+", name):
        return JSONResponse(status_code=404, content={"detail": "not found"})
    path = os.path.join(adminIconsDir, f"{name}.png")
    if not os.path.isfile(path):
        return JSONResponse(status_code=404, content={"detail": "not found"})
    return FileResponse(path, media_type="image/png")

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
    if not adminToken:
        return False
    authHeader = request.headers.get("Authorization")
    if not authHeader:
        return False
    if re.match(r"^Bearer ", authHeader):
        return authHeader.split(" ", 1)[1] == adminToken
    # HTTP Basic lets a browser reach admin pages through its native
    # prompt: any user name, the admin token as password.
    if re.match(r"^Basic ", authHeader):
        try:
            decoded = base64.b64decode(authHeader.split(" ", 1)[1]).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            return False
        _, _, password = decoded.partition(":")
        return password == adminToken
    return False

def authorizeRoom(request: Request):
    """
    Check if request has a valid room token.

    Returns False when PROXY_ROOM_TOKEN is unset, which disables the route
    altogether. The operational token is accepted as well, so a client that
    already holds one does not need a second secret.
    """
    if not roomToken:
        return False
    authHeader = request.headers.get("Authorization")
    if not authHeader or not re.match(r"^Bearer ", authHeader):
        return False
    token = authHeader.split(" ", 1)[1]
    return token == roomToken or token == allowedToken


def findAvailableGateway():
    for key in redisClient.scan_iter(match="gateway:*"):
        value = redisClient.get(key)
        parts = value.split("|")
        gwIp = parts[redis_gw_ip_index]
        state = getPart(parts, redis_gw_state_index)
        if state == "started":
            return [key, gwIp]
    return None

def updateProgressInfo(gw_id: str, parts: list, data: dict):
    recording = data.get("recording_duration")
    streaming = data.get("streaming_duration")
    transcript = data.get("transcript_progress")
    state  = data.get("gw_state")
    room = data.get("room")
    browsing = data.get("browsing")
    peerUri = data.get("peer_uri")
    peerName = data.get("peer_name")
    callStarted = data.get("call_started")
    parts += [""] * (redis_gw_field_count - len(parts) )
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
    parts[redis_gw_room_index] = f"{room}" if room else "None"
    parts[redis_gw_browsing_index] = f"{browsing}" if browsing else "None"
    parts[redis_gw_peer_uri_index] = f"{peerUri}" if peerUri else "None"
    parts[redis_gw_peer_name_index] = f"{peerName}" if peerName else "None"
    parts[redis_gw_call_started_index] = f"{callStarted}" if callStarted else "None"

    mapping = "|".join(parts)
    redisClient.set(f"gateway:{gw_id}", mapping)

def getGatewayStatusFromRedis(gw_id: str):
    rawValue = redisClient.get(f"gateway:{gw_id}")
    if not rawValue:
        return None
    parts = rawValue.split("|")
    gwIp = parts[redis_gw_ip_index]
    room = getPart(parts, redis_gw_room_index)
    state = getPart(parts, redis_gw_state_index)
    media_duration = getPart(parts, redis_gw_media_duration_index)
    transcript = getPart(parts, redis_gw_transcript_progress_index)
    browsing = getPart(parts, redis_gw_browsing_index)
    gwType = getPart(parts, redis_gw_type_index)
    peerUri = getPart(parts, redis_gw_peer_uri_index)
    peerName = getPart(parts, redis_gw_peer_name_index)
    callStarted = getPart(parts, redis_gw_call_started_index)
    return {
        "status": "success",
        "data": {
            "gw_id": gw_id,
            "gw_type": cleanPart(gwType),
            "gw_state": state,
            "room": cleanPart(room),
            "browsing": cleanPart(browsing),
            "peer_uri": cleanPart(peerUri),
            "peer_name": cleanPart(peerName),
            "call_started": cleanPart(callStarted),
            "media_duration": media_duration,
            "transcript_progress": transcript
        }
    }

def normalizeSipUri(uri: str) -> str:
    """
    Accept both "user@domain" and "sip:user@domain".

    Endpoints report their own identity without the scheme, while the gateway
    records it normalised. Mirrors normalizeSipUri() in src/logParse.py.
    """
    cleanUri = (uri or "").strip()
    if not cleanUri:
        return ""
    if cleanUri.startswith("sip:"):
        return cleanUri
    if "@" in cleanUri:
        return "sip:" + cleanUri
    return cleanUri

@app.get("/gateway_id")
async def gatewayIdFromPeerUri(request: Request, peer_uri: str = None):
    """
    GET /gateway_id?peer_uri=<sip uri> - Resolve the gateway currently serving
    a given SIP endpoint.

    Endpoints know their own registration URI but not the identifier of the
    gateway they are calling. This lets a room-side SIP client obtain it in order to issue
    control commands for the duration of the call.

    Only gateways with an established call carry a peer_uri, so an endpoint
    that is not in a call cannot be resolved.
    """
    if not authorizeRoom(request):
        return Response(
            json.dumps({"error": "authorization error"}),
            status_code=401,
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
            media_type="application/json"
        )

    if not peer_uri:
        raise HTTPException(status_code=400, detail="Missing 'peer_uri' parameter")

    wanted = normalizeSipUri(peer_uri).lower()

    # A gateway torn down after a hangup may still hold a mapping until the
    # next monitor cycle, so the most recently established call wins.
    best = None
    for key in redisClient.scan_iter(match="gateway:*"):
        rawValue = redisClient.get(key)
        if not rawValue:
            continue
        parts = rawValue.split("|")

        peerUri = cleanPart(getPart(parts, redis_gw_peer_uri_index))
        if not peerUri or normalizeSipUri(peerUri).lower() != wanted:
            continue

        callStarted = cleanPart(getPart(parts, redis_gw_call_started_index)) or ""
        if best is None or callStarted > best["call_started"]:
            best = {
                "gw_id": key.split(":")[-1],
                "room": cleanPart(getPart(parts, redis_gw_room_index)),
                "browsing": cleanPart(getPart(parts, redis_gw_browsing_index)),
                "call_started": callStarted,
            }

    if not best:
        raise HTTPException(
            status_code=404,
            detail=f"No gateway currently serving '{peer_uri}'"
        )

    return {
        "gw_id": best["gw_id"],
        "room": best["room"],
        "browsing": best["browsing"],
    }

@app.get("/admin/statuses")
async def adminStatus(request: Request):
    """GET /admin/statuses - Get status of all gateways (admin only)"""
    if not authorizeAdmin(request):
        return Response(
            json.dumps({"error": "authorization error"}),
            status_code=401,
            headers={"WWW-Authenticate": 'Basic realm="SIPMediaGW admin", Bearer error="invalid_token"'},
            media_type="application/json"
        )

    # Redis stores pairing:<code> -> gw_id, while the console needs the
    # reverse. Codes have a short TTL, so the value only holds at the
    # time of the request.
    pairingByGateway = {}
    for pairingKey in redisClient.scan_iter(match="pairing:*"):
        pairedGwId = redisClient.get(pairingKey)
        if pairedGwId:
            pairingByGateway[pairedGwId] = pairingKey.split(":", 1)[1]

    result = {}
    for key in redisClient.scan_iter(match="gateway:*"):
        gw_id = key.split(":")[-1]
        raw = redisClient.get(key)
        if not raw:
            continue
        parts = raw.split("|")
        gwIp = parts[redis_gw_ip_index]
        room = getPart(parts, redis_gw_room_index)
        state = getPart(parts, redis_gw_state_index)
        media_duration = getPart(parts, redis_gw_media_duration_index)
        transcript = getPart(parts, redis_gw_transcript_progress_index)
        browsing = getPart(parts, redis_gw_browsing_index)
        gwType = getPart(parts, redis_gw_type_index)
        peerUri = getPart(parts, redis_gw_peer_uri_index)
        peerName = getPart(parts, redis_gw_peer_name_index)
        callStarted = getPart(parts, redis_gw_call_started_index)

        result[gw_id] = {
            "gateway": gwIp,
            "type": cleanPart(gwType),
            "status": state,
            "room": room if room else None,
            "media_duration": media_duration,
            "transcript_progress": transcript,
            "browsing": browsing if browsing else None,
            "peer_uri": peerUri if peerUri else None,
            "peer_name": peerName if peerName else None,
            "call_started": callStarted if callStarted else None,
            "pairing_code": pairingByGateway.get(gw_id)
        }
    return result

async def _fetchAndStoreGatewayStatus(gw_id: str, gw_ip: str, parts: list):
    """
    Fetch /gateway/status from a single gateway and update its Redis entry.
    Used by the periodic monitor and the on‑demand monitor.
    """
    url = f"http://{gw_ip}/gateway/status"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = {"Authorization": f"Bearer {allowedToken}"}
            response = await client.get(url, params={"gw_id": gw_id}, headers=headers)

        data = response.json()
        if data.get("status") == "success":
            updateProgressInfo(gw_id, parts, data.get("data"))
        else:
            print(f"Gateway {gw_id} returned error → delete mapping")
            redisClient.delete(f"gateway:{gw_id}")
    except Exception as exc:
        print(f"[fetchAndStoreGatewayStatus] error contacting {gw_ip}: {exc}")
        redisClient.delete(f"gateway:{gw_id}")

async def monitorOneGateway(gw_id: str, gw_ip: str):
    """Check a single gateway (baresip case) and refresh its Redis entry."""
    raw = redisClient.get(f"gateway:{gw_id}")
    parts = raw.split("|") if raw else []
    await _fetchAndStoreGatewayStatus(gw_id, gw_ip, parts)

# Background task to monitor gateways
async def monitorGateways(intervalSeconds: int = 30):

    while True:
        print("Checking gateway states...")
        for key in redisClient.scan_iter(match="gateway:*"):
            gw_id = key.split(":")[-1]
            value = redisClient.get(key)
            if not value:
                continue

            parts = value.split("|")
            gw_ip = parts[redis_gw_ip_index]

            await _fetchAndStoreGatewayStatus(gw_id, gw_ip, parts)

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

@app.get("/interact")
async def interact(request: Request):

    gwId = request.query_params.get("gwId") or request.query_params.get("gw_id")
    if not gwId:
        pairingCode = request.query_params.get("pairingCode")
        if pairingCode:
            # Look‑up the gw_id stored under the pairing code
            resolvedGwId = redisClient.get(f"pairing:{pairingCode}")
            if resolvedGwId:
                # Redirect to the same endpoint with the resolved gw_id
                redirectUrl = "{}?gwId={}".format(str(request.url).split('?')[0], resolvedGwId)
                return RedirectResponse(url=redirectUrl, status_code=302)
            else:
                # Return pairing.html and inject a JS var so the page can display a translated error
                try:
                    with open("pairing.html", "r", encoding="utf-8") as f:
                        html_form = f.read()
                except FileNotFoundError:
                    raise HTTPException(status_code=500, detail="pairing.html not found on server")
                # inject safe JS literals
                error_msg = "Invalid pairing code"
                injection_script = (
                    f'<script>window.SERVER_ERROR = {json.dumps(error_msg)}; '
                    f'window.SERVER_PAIRING_CODE = {json.dumps(pairingCode)};</script>'
                )
                # insert the script before the first existing <script> so the page's JS sees it
                if "<script" in html_form:
                    html_with_msg = html_form.replace("<script", injection_script + "<script", 1)
                else:
                    # fallback: insert before </head>
                    html_with_msg = html_form.replace("</head>", injection_script + "</head>", 1)
                return Response(content=html_with_msg, media_type="text/html")
        else:
            with open("pairing.html", "r", encoding="utf-8") as f:
                html_form = f.read()
            return Response(content=html_form, media_type="text/html")

    rawData = redisClient.get(f"gateway:{gwId}")
    if not rawData:
        raise HTTPException(status_code=404, detail=f"Gateway '{gwId}' not found")

    parts = rawData.split("|")
    gwIp = parts[redis_gw_ip_index]

    gwUrl = f"http://{gwIp}/gateway/interact"
    headers = {"Authorization": request.headers.get("Authorization", "")}
    params = dict(request.query_params)

    gwResponse = await proxyToGateway(gwUrl, request, params, None, headers)

    content = gwResponse.content
    mediaType = gwResponse.headers.get("content-type", "text/html")
    return Response(content=content, status_code=gwResponse.status_code, media_type=mediaType)

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
            json.dumps({"error": "authorization error invalid_token "}),
            status_code=401,
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
            media_type="application/json"
        )

    browsing = (await request.json()).get("browsing")
    if not browsing:
        raise HTTPException(status_code=400, detail="Missing 'browsing' parameter")

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
            parts[redis_gw_room_index] = room if room else None
            parts[redis_gw_browsing_index] = browsing if browsing else None
            mapping = "|".join(parts)
            redisClient.set(f"gateway:{gw_id}", mapping)
        else:
            raise HTTPException(status_code=503, detail=responseJson.get("error").get("detail"))
    except Exception:
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
            parts += [""] * (redis_gw_field_count - len(parts))
            parts[redis_gw_room_index] = ''
            parts[redis_gw_browsing_index] = ''
            parts[redis_gw_peer_uri_index] = ''
            parts[redis_gw_peer_name_index] = ''
            parts[redis_gw_call_started_index] = ''
            parts[redis_gw_state_index] = "stopped"
            mapping = "|".join(parts)
            redisClient.set(f"gateway:{gw_id}", mapping)
            responseJson["status"] = "success"
        else:
            responseJson["status"] = "error"
    except Exception as e:
        print("Failed to parse JSON response:", e)
        responseJson = {
            "status": "error",
            "error": "Failed to parse gateway response",
            "data": gwResponse.json() if gwResponse.content else None
        }

    return Response(
        content=json.dumps(responseJson),
        status_code=gwResponse.status_code,
        media_type="application/json"
    )

@app.get("/status")
@app.get("/progress")
async def statusGateway(request: Request, gw_id: str = None, room: str = None):
    """GET /status?gw_id=gatewayName - Get gateway status"""
    # if not authorize(request):
    #     return Response(
    #         json.dumps({"error": "authorization error"}),
    #         status_code=401,
    #         headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
    #         media_type="application/json"
    #     )

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
            gwRoom = getPart(parts, redis_gw_room_index)
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

    # ----- Refresh baresip gateways on demand --------------------
    gw_type = getPart(parts, redis_gw_type_index)
    if gw_type == "baresip":
        # call the on‑demand monitor to get a fresh status
        await monitorOneGateway(gw_id, gwIp)

        # reload the (possibly updated) mapping
        rawValue = redisClient.get(f"gateway:{gw_id}")
        if not rawValue:
            raise HTTPException(
                status_code=404,
                detail=f"Gateway '{gw_id}' unreachable after on‑the‑fly check"
            )
        parts = rawValue.split("|")
    # ------------------------------------------------------------------

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

async def genericGatewayProxy(request: Request, endpoint: str):
    """Generic proxy for gateway endpoints like /command, /ivrConfig, /status, /icon/*"""
    # Retrieve gw_id from query params (GET) or JSON body (POST)
    gw_id = request.query_params.get("gw_id")
    if request.method != "GET":
        try:
            body = await request.json()
            gw_id = body.get("gw_id") or gw_id
        except Exception:
            pass

    if not gw_id:
        raise HTTPException(status_code=400, detail="Missing 'gw_id' parameter")

    raw_value = redisClient.get(f"gateway:{gw_id}")
    if not raw_value:
        raise HTTPException(status_code=404, detail=f"Gateway '{gw_id}' not found")

    parts = raw_value.split("|")
    gw_ip = parts[redis_gw_ip_index]

    isWorking = (
        len(parts) > redis_gw_state_index
        and parts[redis_gw_state_index] == "working"
    )
    if not isWorking:
        print(f"Gateway '{gw_id}' is stopped, cannot send commands")
        raise HTTPException(status_code=403, detail=f"Gateway '{gw_id}' is stopped, cannot send commands")

    params = dict(request.query_params)
    headers = {"Authorization": request.headers.get("Authorization", "")}
    body = await request.json() if request.method != "GET" else None
    gw_url = f"http://{gw_ip}/gateway/{endpoint}"

    gw_response = await proxyToGateway(gw_url, request, params, body, headers)

    # Try to decode JSON; if it fails, return raw content (useful for binary icons)
    try:
        response_json = gw_response.json()
        content = json.dumps(response_json)
        media_type = "application/json"
    except Exception:
        content = gw_response.content
        media_type = gw_response.headers.get("content-type", "application/octet-stream")

    return Response(content=content, status_code=gw_response.status_code, media_type=media_type)

@app.api_route("/command", methods=["POST"])
async def commandGateway(request: Request):
    return await genericGatewayProxy(request, "command")

@app.api_route("/ivrConfig", methods=["GET"])
async def ivrConfigGateway(request: Request):
    return await genericGatewayProxy(request, "ivrConfig")

@app.api_route("/browsing", methods=["GET"])
async def ivrConfigGateway(request: Request):
    return await genericGatewayProxy(request, "browsing")

@app.api_route("/status", methods=["GET"])
async def statusGatewayProxy(request: Request):
    return await genericGatewayProxy(request, "status")

@app.api_route("/icon/{icon_name}", methods=["GET"])
async def iconGateway(request: Request, icon_name: str):
    return await genericGatewayProxy(request, f"icon/{icon_name}")

@app.api_route("/logo/{logo_name}", methods=["GET"])
async def logoGateway(request: Request, logo_name: str):
    return await genericGatewayProxy(request, f"logo/{logo_name}")

@app.post("/register")
async def registerGateway(request: Request):
    def generatePairingCode(length: int = 5) -> str:
        return "".join(random.choices(string.ascii_uppercase + string.digits, k=length))

    if not authorize(request):
        return Response(
            json.dumps({"error": "authorization error"}),
            status_code=401,
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
            media_type="application/json",
        )

    try:
        body   = await request.json()
        gwIp   = body.get("gw_ip")
        gwId  = body.get("gw_id")
        gwType = body.get("gw_type", "media")
        pairingCode = body.get("pairing_code")
        pairingTimeOut = body.get("pairing_timeout")
        # If a pairing_code was provided, ensure we don't overwrite an existing mapping
        if pairingCode:
            if redisClient.exists(f"pairing:{pairingCode}"):
                # pairing code already mapped, keep existing mapping and do not overwrite
                existingGwId = redisClient.get(f"pairing:{pairingCode}")
                # Use existing gwId for consistency (ignore the gw_id supplied if different)
                gwId = existingGwId
            else:
                pairingCode = generatePairingCode()
                redisClient.setex(f"pairing:{pairingCode}", pairingTimeOut, gwId)
        else:
            pairingCode = generatePairingCode()
            redisClient.setex(f"pairing:{pairingCode}", pairingTimeOut, gwId)

        if not gwIp or not gwId:
            raise HTTPException(status_code=400, detail="Missing 'gwIp' or 'gw_id'")

        # Look for existing mapping
        existing_raw = redisClient.get(f"gateway:{gwId}")
        if existing_raw:
            # Keep status based metrics
            parts = existing_raw.split("|")
            parts += [""] * (redis_gw_field_count - len(parts))
            gwState = parts[redis_gw_state_index]
            startTime = parts[redis_gw_start_time_index]
            roomName        = parts[redis_gw_room_index]
            mediaduration   = parts[redis_gw_media_duration_index]
            transcriptprog  = parts[redis_gw_transcript_progress_index]
            browsing      = parts[redis_gw_browsing_index]
            peerUri       = parts[redis_gw_peer_uri_index]
            peerName      = parts[redis_gw_peer_name_index]
            callStarted   = parts[redis_gw_call_started_index]
        else:
            # No mapping found => reset
            gwState = "started"
            startTime = dt.datetime.now().isoformat()
            roomName = None
            mediaduration   = "0"
            transcriptprog  = "0"
            browsing      = None
            peerUri       = None
            peerName      = None
            callStarted   = None

        # Build new mapping
        # format : gwIp|state|type|room|startTime|media|transcript|browsing|peerUri|peerName|callStarted
        gwValue = (
            f"{gwIp}|{gwState}|{gwType}|{roomName}|{startTime}|"
            f"{mediaduration}|{transcriptprog}|{browsing}|{peerUri}|{peerName}|{callStarted}"
        )
        redisClient.set(f"gateway:{gwId}", gwValue)
        print(f"Gateway registered / updated: {gwId} ({gwIp})")
        return Response(
            content=json.dumps({"status": "success",
                                "gw_id": gwId, "gw_ip": gwIp,
                                "pairing_code": pairingCode}),
            status_code=200,
            media_type="application/json",
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))

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
