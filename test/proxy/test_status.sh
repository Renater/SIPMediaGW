# Test script for adding a gateway VM
#!/bin/bash


curl -s -H "Authorization: Bearer 1234" -H "Content-Type: application/json" \
-X GET http://127.0.0.1:9000/progress?room=$1 | jq



