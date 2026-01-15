# Test script to get the status of a gateway
#!/bin/bash


curl -H "Authorization: Bearer 1234" -H "Content-Type: application/json" \
-X POST http://127.0.0.1:8100/gateway/command \
-d '{"gw_id":"'$1'", "payload": {"action": "ping"} }' | jq



