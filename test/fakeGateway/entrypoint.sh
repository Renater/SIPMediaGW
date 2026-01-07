# Entrypoint for the fake gateway service
#!/bin/bash

cleanup() {
   echo "Cleaning up fake gateway service..."
   curl -H "Authorization: Bearer 1234" -X POST http://localhost:80/gateway/remove_gw -d '{"gwName": "'"$GW_NAME1"'"}'
   curl -H "Authorization: Bearer 1234" -X POST http://localhost:80/gateway/remove_gw -d '{"gwName": "'"$GW_NAME2"'"}'
}

# Trap signals for cleanup
trap cleanup SIGINT SIGQUIT SIGTERM

CONTAINER_NAME=${CONTAINER_NAME:-defaultgw}

# Start the fake gateway service
echo "Starting fake gateway service... $CONTAINER_NAME ."
/usr/bin/python3 HTTPLauncher.py 80  2>&1 | logger -t HTTPLauncher &
SERVICE_PID=$!

sleep 2
GW_NAME1=$(curl  -s -H "Authorization: Bearer 1234" -X POST http://localhost:80/gateway/add_gw -d '{"gwIp": "'"$CONTAINER_NAME"'"}' | jq -r .details.gwName)
GW_NAME2=$(curl  -s -H "Authorization: Bearer 1234" -X POST http://localhost:80/gateway/add_gw -d '{"gwIp": "'"$CONTAINER_NAME"'"}' | jq -r .details.gwName)

echo "Gateway service started."

# Wait for service so PID1 receives signals and trap works
wait $SERVICE_PID