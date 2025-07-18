# Proxy API for Gateway Room Management

This FastAPI-based proxy handles the allocation, tracking, and lifecycle management of media gateways per "room" identifier. The system uses Redis to maintain mappings between room names and gateway IPs.

## Redis Mapping Format

Each room is mapped in Redis under the key `room:{room_name}` with the following pipe-delimited value format:

```
<gateway_ip>|<state>|<recording_duration>|<transcript_progress>
```

- `gateway_ip`: IP address of the assigned gateway.
- `state`: `"started"` or `"stopped"`.
- `recording_duration`: optional (e.g., `00:10:32`) – filled during background progress tracking.
- `transcript_progress`: optional (e.g., `50%`) – filled during background progress tracking.

### Example:
```bash
> redis-cli GET room:math101
192.168.1.12|started|00:02:43|80%
```

---

## Exposed Endpoints

### `POST /start?room=roomName`
Assigns an available gateway to the specified room. Returns error if none available.

### `POST /stop?room=roomName`
Stops the gateway associated with the room. The mapping is marked as `stopped` (not deleted).

### `GET /progress?room=roomName`
Returns gateway progress info. This is the **only action allowed** on a stopped gateway.

### `GET /status`
Returns the status of all currently mapped rooms with gateway state and progress info.

### `GET /assets/assets.tar.xz`
Static download endpoint (for e.g. resources needed by the gateways).

---

## Background Monitoring

A background task (`monitorGateways`) runs periodically to:
- Poll the `/progress` endpoint on all mapped gateways.
- If a gateway is both `stopped` and returns `gw_state = down`, the Redis entry is deleted.
- Otherwise, updates the Redis value with recording/transcript progress.

---

## Authorization

All endpoints (except `/assets/...`) require a `Bearer` token in the `Authorization` header.

Example:
```bash
curl -H "Authorization: Bearer 1234" http://localhost:8080/status
```

---

##  Notes

- Gateway IPs are allocated only if not currently in use (`findAvailableGateway`).
- The mapping format is minimal and avoids Redis hash complexity for easier debugging/maintenance.
- Progress info is updated **only in the background task**, not during active actions.
