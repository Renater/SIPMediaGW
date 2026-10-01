# Proxy API for Gateway Room Management

This FastAPI-based proxy handles the allocation, tracking, and lifecycle management of media gateways per "room" identifier. The system uses Redis to maintain mappings between room names and gateway IPs.

## The entry of a gateway in Redis

Each gateway is stored under the key `gateway:<gw_id>` as a JSON object
(`gwFields` in `proxy.py`; a field added there is read everywhere by name):

| Field | Written by | Meaning |
|---|---|---|
| `gw_ip` | `/register` | the launcher's address, `HOST_IP:GW_API_PORT` (port 8100 by default) |
| `gw_state` | `/register`, `/start`, `/stop`, the monitor, the media scaler | `created`, `started`, `stopped`, `deleted`; `stopping` from the scaler |
| `gw_type` | `/register` | `media`, `baresip`, `recording`, `streaming` |
| `room`, `browsing`, `peer_uri`, `peer_name`, `call_started` | the monitor, from `/gateway/status` | what the container is doing; `call_started` is UTC, `Z`-suffixed, written by the gateway at CALL_ESTABLISHED |
| `media_duration`, `transcript_progress` | the monitor | recording and streaming containers |
| `start_time` | `/register` | when the entry was created |

`created`/`deleted` describe the VM, `started`/`stopped` the container on it.
An empty field or the string `"None"` (left by the former pipe-separated
form) both read as absent.

```bash
> redis-cli GET gateway:gw01
{"gw_ip": "192.0.2.21:8100", "gw_state": "started", "gw_type": "media", "room": "wqpmzrtkcx", ...}
```

Pairing codes live under `pairing:<code>` → `gw_id`, with a short TTL.

## The derived state

`/admin/statuses` adds a `state` to every entry, worked out once in
`deriveState()` so that every reader says the same thing:

| `state` | When |
|---|---|
| `free` | `gw_state` is `created` or `stopped`: a slot `/start` can allocate |
| `idle` | `started`, no room, no peer: the container waits for a call |
| `ivr` | `started`, a peer or a `call_started`, no room: the caller is on the voice menu |
| `call` | `started` with a room: in conference (a peer is not required: browsing-only gateways) |
| `gone` | `deleted` |
| `other` | anything else, `stopping` included |

Readers must not derive the state themselves from `status`/`room`/`peer_*`.

---

## Exposed endpoints (matching proxy.py)

Who may call what, as `proxy.py` checks it today:

| Routes | Check at the proxy |
|---|---|
| `/start`, `/stop`, `/register`, `/unregister` | `Authorization: Bearer <PROXY_TOKEN>` |
| `/admin/statuses` | `Bearer <PROXY_ADMIN_TOKEN>` (or Basic, the token as password); unset token = route closed |
| `/gateway_id` | `Bearer <PROXY_ROOM_TOKEN>` |
| `/status`, `/progress` | none: the check is commented out in `statusGateway` |
| `/command`, `/ivrConfig`, `/browsing`, `/icon/*`, `/logo/*` | none at the proxy: relayed to the gateway's launcher with the caller's `Authorization` header; `/command` only while `gw_state` is `started` |
| `/`, `/pairing`, `/interact`, their static files, `/assets/*` | none (pages); `/pairing/resolve` is rate-limited per client |

### POST /start
Start a gateway for a room (body JSON).
- Request JSON:
  ```json
  { "room": "roomName" }
  ```
- Behaviour: picks a free gateway (`gw_state` `created` or `stopped`), forwards the request to the gateway's `/gateway/start` with `gw_id` added, and sets `gw_state` to `started` with the room.
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
- Behaviour: forwards to the gateway's `/gateway/stop`. On success the proxy sets `gw_state` to `deleted` and clears the call fields; the next monitor cycle, once the launcher reports the container down, writes `stopped`.
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
        "gw_id": "gw01",
        "gw_type": "media",
        "gw_state": "started",
        "room": "math101",
        "browsing": "visio",
        "peer_uri": "sip:room12@sip.sample.org",
        "peer_name": "Room 12",
        "call_started": "2026-09-24T08:20:48Z",
        "media_duration": null,
        "transcript_progress": null
      }
    }
    ```
  - 400 — Missing parameters
  - 404 — Gateway or room not found

### GET /admin/statuses (admin only)
Every registered gateway, keyed by `gw_id`, with the derived `state`. This is
what the Manager reads; its shape is pinned by `test/proxy/test_proxy.py` on
this side and by `manager/tests/fixtures/admin_statuses.json` on the Manager's.
- Response example:
  ```json
  {
    "gw01": {
      "gateway": "192.0.2.21:8100",
      "type": "media",
      "status": "started",
      "state": "call",
      "room": "wqpmzrtkcx",
      "media_duration": null,
      "transcript_progress": null,
      "browsing": "visio",
      "peer_uri": "sip:room12@sip.sample.org",
      "peer_name": "Room 12",
      "call_started": "2026-09-24T08:20:48Z",
      "pairing_code": null
    },
    "gw02": {
      "gateway": "192.0.2.22:8100",
      "type": "media",
      "status": "created",
      "state": "free",
      "room": null,
      "media_duration": null,
      "transcript_progress": null,
      "browsing": null,
      "peer_uri": null,
      "peer_name": null,
      "call_started": null,
      "pairing_code": null
    }
  }
  ```

### POST /command
Forward a command to a gateway.
- Query: `?gw_id=gw01`
- Body: forwarded as-is to gateway.
- Note: commands are rejected (403) unless gateway state == "started".
- Response: proxied gateway response.

### POST /register
Register a gateway (gateway calls proxy on startup).
- Request JSON:
  ```json
  { "gw_ip": "192.0.2.21:8100", "gw_id": "gw01", "gw_type": "media",
    "pairing_code": "123456", "pairing_timeout": 90 }
  ```
- Behaviour: creates the Redis entry (see above) with `gw_state` set to
  `created`, and a pairing code when the gateway asked for one.
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

A background task polls each gateway at `/gateway/status` every 30 s and:
- updates `gw_state`, `room`, `browsing`, `peer_*`, `call_started`,
  `media_duration` and `transcript_progress` in its entry;
- removes the entry when the gateway answers an error or cannot be reached.

---

## Supervision

The console that used to be served on `/admin/` is gone: the Manager
(`manager/`) reads `/admin/statuses` and shows the pool, with the call history
and the reports beside it. `/admin/statuses` stays, with the same admin token
(Bearer, or Basic with the token as password).

## Authorization examples

The examples use port 80, the one `docker-compose.yml` publishes.

Normal requests:
```bash
curl -H "Authorization: Bearer $PROXY_TOKEN" -X POST -d '{"room":"math101"}' http://localhost/start
```

Admin requests (`PROXY_ADMIN_TOKEN` must be set, there is no default):
```bash
curl -H "Authorization: Bearer $PROXY_ADMIN_TOKEN" http://localhost/admin/statuses
# HTTP Basic is accepted too (any user name, the admin token as password):
curl -u admin:$PROXY_ADMIN_TOKEN http://localhost/admin/statuses
```