#!/bin/bash

# Start the proxy and Redis containers
docker compose -f test/proxy/docker-compose.yml up -d

# Set environment variables for the gateway to use the proxy

export GW_PROXY=http://localhost:9010

# Run the gateway container with the environment variables
/bin/bash deploy/services/start_all_gateways.bash