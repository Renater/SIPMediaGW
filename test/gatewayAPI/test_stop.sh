# Test script for stopping a gateway VM
#!/bin/bash


curl -H "Authorization: Bearer 1234" -H "Content-Type: application/json" \
-X POST http://localhost:8100/gateway/stop \
-d '{
"gw_id": "'$1'"
}' | jq



