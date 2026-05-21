# Tools and quick commands to run a minimal test environment for SIPMediaGW Proxy module

## Setup environment

Start required services (Redis, proxyAPI and FakeSIPMediaGW):

```bash
docker-compose -f deploy/docker-compose.yml up -d redis
docker-compose -f deploy/proxyAPI/docker-compose.yml up --build -d
docker-compose -f deploy/FakeSIPMediaGW/docker-compose.yml up --build -d
```

Proxy API is expected to listen on port 80 in this test setup.

## Run tests (example requests)

Use the normal token `1234` for regular operations (start/stop/progress/command/register/unregister).
Use the admin token `admin-secret-key` for admin-only endpoints (e.g. `/admin/statuses`).

- Start a recording (POST /start)
```bash
curl -H "Content-Type: application/json" \
  -H "Authorization: Bearer 1234" \
  -X POST http://localhost:80/start \
  -d '{
    "recipientMail": "user@example.com",
    "audio_only": true,
    "transcript": false,
    "room": "test-room-001"
  }'
```
Réponse attendue : JSON contenant au minimum un identifiant de gateway / statut.

- Stop a recording (POST /stop)
```bash
curl -H "Content-Type: application/json" \
  -H "Authorization: Bearer 1234" \
  -X POST http://localhost:80/stop \
  -d '{
    "gw_id": "smgw-001"
  }'
```

- Get status or progress for a gateway (GET /status or GET /progress)
```bash
curl -H "Content-Type: application/json" \
  -H "Authorization: Bearer 1234" \
  "http://localhost:80/status?gw_id=smgw-001"
```

- Send a command to a gateway (GET or POST /command)
```bash
curl -H "Content-Type: application/json" \
  -H "Authorization: Bearer 1234" \
  -X POST "http://localhost:80/command?gw_id=smgw-001" \
  -d '{"action":"ping"}'
```

- Register / unregister a gateway (gateway-side or admin tool)
```bash
curl -H "Content-Type: application/json" \
  -H "Authorization: Bearer 1234" \
  -X POST http://localhost:80/register \
  -d '{"gwIp":"192.168.1.12","gwName":"gw01","gwType":"media"}'

curl -H "Content-Type: application/json" \
  -H "Authorization: Bearer 1234" \
  -X POST http://localhost:80/unregister \
  -d '{"gwName":"gw01"}'
```

- Admin: list all gateways (GET /admin/statuses)
```bash
curl -H "Authorization: Bearer admin-secret-key" \
  http://localhost:80/admin/statuses
```

## Notes

- Ensure Redis is reachable by the proxy (check docker-compose networking).
- Tokens shown here are for tests only; replace with secure values in production.
