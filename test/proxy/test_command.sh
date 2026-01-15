# Test script for adding a gateway VM
#!/bin/bash


curl -s -H "Authorization: Bearer 1234" -H "Content-Type: application/json" \
-X POST http://localhost:9000/command \
-d '{
"gw_id": "'$1'",
"payload": {
"action": "ping"
}
}' | jq



