# Test script for adding a gateway VM
#!/bin/bash


curl -s -H "Authorization: Bearer 1234" -H "Content-Type: application/json" \
-X POST http://localhost:9000/start \
-d '{"room": "'$1'",
"type": "recording",
"transcript": "false",
"audio_only": "false",
"recipient_mail": "toto@test.fr"}' | jq



