# SIP Media Gateway API — Documentation (updated)

## Overview
The HTTPLauncher implements a small HTTP API to start, stop, query and send commands to SIP/Media gateways. Authentication is done with a Bearer token (the proxy or client must provide it).

## Authentication
All requests must include an `Authorization` header:
```
Authorization: Bearer <token>
```

## Response envelope
All endpoints use a common response envelope:
- status: "success" | "error"
- data: optional object with endpoint-specific data
- error: optional object { code?, message? }

Common HTTP codes:
- 200 OK — success
- 422 Unprocessable Entity — validation error
- 404 Not Found — resource not found
- 500 Internal Server Error — internal error

---

## Endpoints

### POST /gateway/start
Start a gateway instance (script or container, depending on configuration).

Request JSON (StartRequest example):
```json
{
  "type": "Record",
  "room": "room_name",
  "gw_id": "gw01",
  "webrtc_domain": { "provider": { "name": "x", "domain": "example.com" } },
  "from_id": "optional",
  "prefix": "optional",
  "rtmp_dst": "rtmp://...",
  "dial": "sip:...",
  "loop": false,
  "transcript": false,
  "audio_only": true,
  "api_key": "optional",
  "recipient_mail": "user@example.com",
  "main_app": "recording"
}
```

Success (200):
```json
{
  "status": "success",
  "data": {
    "processing_state": "working",
    "gw_id": "gw01"
  }
}
```

Errors:
- 422 — invalid payload (missing required fields or wrong types)
- 500 — start failure (error.message contains details)

### POST /gateway/stop
Stop a gateway instance.

Request JSON (StopRequest):
```json
{
  "gw_id": "gw01",
  "force": true           // optional
}
```

Success (200):
```json
{
  "status": "success",
  "data": {
    "processing_state": "stopped"
  }
}
```

Errors:
- 404 — gw_id not found
- 500 — stop failure

### GET /gateway/status
Get status for a gateway.

Query parameter:
- gw_id (required)

Example:
GET /gateway/status?gw_id=gw01

Success (200):
```json
{
  "status": "success",
  "data": {
    "gw_state": "up|down",
    "gw_id": "gw01",
    "recording_duration": "HH:MM:SS",
    "transcript_progress": "0%|45%|100%",
    "detail": "optional textual detail"
  }
}
```

Errors:
- 400 — missing gw_id
- 404 — gateway not found

### POST /gateway/command
Send an arbitrary command payload to a gateway. The JSON body is forwarded to the gateway handler.

Query parameter:
- gw_id (required)

Request body: arbitrary JSON (command payload)

Success (200):
```json
{
  "status": "success",
  "data": {
    "ack": true,
    "received": { /* echoed payload from gateway or launcher */ }
  }
}
```

Errors:
- 404 — gateway not found
- 403 — gateway in a stopped state (commands disallowed)

---

## Notes on behavior
- The launcher may start containers or run local scripts depending on the use_container configuration.
- The field processing_state indicates internal lifecycle ("working", "stopped", etc).
- Validation errors return 422 from FastAPI when request schema does not match expected model.
- The API returns the standardized response envelope to ease proxy integration.

## Examples (curl)

Start:
```bash
curl -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -X POST http://localhost:8100/gateway/start \
  -d '{"type":"Record","room":"test-room","gw_id":"gw01","main_app":"recording"}'
```

Stop:
```bash
curl -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -X POST http://localhost:8100/gateway/stop \
  -d '{"gw_id":"gw01"}'
```

Status:
```bash
curl -H "Authorization: Bearer <token>" \
  -X GET \
  "http://localhost:8100/gateway/status?gw_id=gw01"
```

Command:
```bash
curl -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -X POST "http://localhost:8100/gateway/command?gw_id=gw01" \
  -d '{"action":"ping"}'
```

---

