# Proxy API for Gateway Room Management

This FastAPI-based proxy handles the allocation, tracking, and lifecycle management of media gateways per "room" identifier. The system uses Redis to maintain mappings between room names and gateway IPs.

## Redis mapping format (updated)

Each gateway is mapped under key `gateway:{gw_id}` with 7 pipe-delimited fields:

```
<gw_ip>|<state>|<type>|<room>|<start_time>|<media_duration>|<transcript_progress>
```

Indexes used in code:
- 0: gw_ip
- 1: state (started | working | stopped)
- 2: type (recorder | streamer | sip | media, ...)
- 3: room (or "None")
- 4: start_time (ISO)
- 5: media_duration (e.g. "00:05:12" or "0")
- 6: transcript_progress (e.g. "45%")

Example:
```bash
> redis-cli GET gateway:gw01
192.168.1.12|working|recorder|math101|2025-01-01T12:00:00|00:05:12|45%
```

---

## Exposed endpoints (matching proxy.py)

All endpoints (except `/assets/...`) require an Authorization header:
Authorization: Bearer <token>

- Use `allowedToken` for normal operations (start/stop/progress/command/register/unregister).
- Use `adminToken` for admin-only endpoints.

### POST /start
Start a gateway for a room (body JSON).
- Request JSON:
  ```json
  { "room": "roomName" }
  ```
- Behaviour: picks an available gateway (state == started), forwards request to the gateway `/gateway/start` with added `gw_id`, updates Redis to set state=working and room.
- Responses:
  - Success — proxied gateway response (typically 200 with status success)
  - 400 — Missing 'room'
  - 503 — No available gateways

### POST /stop
Stop a gateway (body JSON).
- Request JSON:
  ```json
  { "gw_id": "gw01" }
  ```
- Behaviour: forwards to gateway `/gateway/stop`. On success proxy marks gateway state stopped and clears room in Redis.
- Responses:
  - Success — proxied gateway response (status success)
  - 400 — Missing 'gw_id'
  - 404 — No mapping found for provided gw_id

### GET /status and GET /progress
Get per-gateway status/progress. Query by gw_id or room.
- Query params:
  - gw_id (preferred) or room
- Examples:
  - /status?gw_id=gw01
  - /progress?room=math101
- Behaviour: returns the status stored in Redis for the gateway (no external call unless necessary).
- Responses:
  - 200 — success
    ```json
    {
      "status": "success",
      "data": {
        "gw_id": "192.168.1.12",
        "gw_state": "working",
        "room": "math101",
        "media_duration": "00:05:12",
        "transcript_progress": "45%"
      }
    }
    ```
  - 400 — Missing parameters
  - 404 — Gateway or room not found

### GET /admin/statuses (admin only)
Return status of all gateways. Requires admin Bearer token.
- Response example:
  ```json
  {
    "gw01": {
      "gateway": "192.168.1.12",
      "status": "working",
      "room": "math101",
      "media_duration": "00:05:12",
      "transcript_progress": "45%"
    },
    "gw02": {
      "gateway": "192.168.1.13",
      "status": "stopped",
      "room": null,
      "media_duration": null,
      "transcript_progress": null
    }
  }
  ```

### /command (GET or POST)
Forward a command to a gateway.
- Query: `?gw_id=gw01`
- Body: forwarded as-is to gateway.
- Note: commands are rejected (403) unless gateway state == "working".
- Response: proxied gateway response.

### POST /register
Register a gateway (gateway calls proxy on startup).
- Request JSON:
  ```json
  { "gw_ip": "192.168.1.12", "gw_id": "gw01", "gw_type": "media" }
  ```
- Behaviour: creates Redis entry:
  ```
  <gw_ip>|started|<gw_type>|None|<start_time>|0|0
  ```
- Responses:
  - 200 — success
  - 400 — missing fields

### POST /unregister
Unregister / remove gateway from proxy.
- Request JSON:
  ```json
  { "gw_id": "gw01" }
  ```
- Behaviour: deletes Redis key.
- Responses:
  - 200 — success
  - 404 — gateway not found

### GET /assets/{file_name}
Static download endpoint (unchanged). Example: GET /assets/assets.tar.xz

---

## Background monitoring

A background task polls each gateway at `/gateway/status` and:
- updates media_duration / transcript_progress / state in Redis using the 7-field format;
- if the gateway API reports non-existing or is unreachable, the Redis mapping is removed.

---

## Authorization examples

Normal requests:
```bash
curl -H "Authorization: Bearer 1234" -X POST -d '{"room":"math101"}' http://localhost:9000/start
```

Admin requests:
```bash
curl -H "Authorization: Bearer admin-secret-key" http://localhost:9000/admin/statuses
```