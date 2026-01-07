# Test script for adding a gateway VM
#!/bin/bash


curl -s -H "Authorization: Bearer admin-secret-key" -H "Content-Type: application/json" \
-X GET http://127.0.0.1:9000/admin/statuses | jq



