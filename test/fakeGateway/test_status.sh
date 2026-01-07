# Test script for adding a gateway VM
#!/bin/bash


curl -H "Authorization: Bearer 1234" -H "Content-Type: application/json" \
-X GET http://127.0.0.1:8000/gateway/status?gw_id=$1 \
 | jq



