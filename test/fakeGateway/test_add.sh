# Test script for adding a gateway VM
#!/bin/bash


curl -H "Authorization: Bearer 1234" -H "Content-Type: application/json" \
-X POST http://localhost:8000/gateway/add_gw \
-d '{"gwIp": "192.168.1.100", "gwType": "media"}' | jq



