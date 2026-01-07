#!/bin/bash
# Stop all running gateway containers and unregister them from the Proxy API
i=0;
while docker inspect gw$i > /dev/null 2>&1;
do
    GW_NAME=$(docker inspect gw$i |grep "GW_NAME="| tr -d '"', | cut -d= -f2)
    GW_PROXY=$(docker inspect gw$i |grep "GW_PROXY="| tr -d '"', | cut -d= -f2)
    echo "Unregistering gateway $GW_NAME from Proxy API"
    curl -s -X POST "$GW_PROXY/unregister" -H "Content-Type: application/json"  -H "Authorization: Bearer 1234" -d "{\"gw_id\":\"$GW_NAME\"}";
    if docker inspect gw$i | grep -q '"Running": true'; then
        echo "Container gw$i is running"
        docker stop gw$i >/dev/null 2>&1;
    fi
    docker rm gw$i >/dev/null 2>&1;
    echo "Processed container gw$i"
    i=$((i+1));
done

i=0;
while docker inspect transcript$i > /dev/null 2>&1;
do
    docker rm transcript$i >/dev/null 2>&1;
    echo "Processed container transcript$i"
    i=$((i+1));
done

docker container prune --force > /dev/null
rm /tmp/sipmediagw*.lock 2>/dev/null
pkill -f "HTTPLauncher:app"