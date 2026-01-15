# Test script for starting a gateway 
#!/bin/bash


curl -H "Authorization: Bearer 1234" -H "Content-Type: application/json" \
-X POST http://localhost:8100/gateway/start \
-d '{"webrtc_domain": {"jitsi": {"name": "Jitsi Meet (meet.jit.si)", "domain": "rendez-vous.renater.fr"}}, 
"gw_id": "'$1'",
"main_app": "recording",
"from_id": "user1",
"prefix": "",
"room": "testroom",
"loop": false,
"transcript": "true",
"audio_only": "false",
"recipient_mail": "dfetis@gmail.com"}' | jq



