#!/bin/bash
# Stop the local SIPMediaGW test environment started by start.sh.
#   ./stop.sh            stop containers, unload modules start.sh loaded
#   ./stop.sh --purge    also remove the Kamailio DB volume and gw_net
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
STATE=/tmp/sipmediagw-local.state
LOOP_PID=/tmp/sipmediagw-local.loop.pid
cd "$ROOT" || exit 1

# Kill the restart watcher first, or stopping gw0 would recreate it.
if [[ -f "$LOOP_PID" ]]; then
    kill -- -"$(cat "$LOOP_PID")" 2> /dev/null
    rm -f "$LOOP_PID"
fi

# Values only needed for compose to parse the files.
export ID=0 VIDEO_DEV=null HOST_IP=${HOST_IP:-127.0.0.1} GW_NAME="" HOST_TZ="" CHECK_REG="" \
       ROOM="" PREFIX="" INIT="" RTMP_DST="" FS_API_KEY="" FS_USER_MAIL="" FS_RECIPIENT_MAIL="" \
       WITH_TRANSCRIPT="" PULSE_SERVER=""

docker compose -p localgw down --remove-orphans
if [[ "${1:-}" == "--purge" ]]; then
    docker compose -f deploy/docker-compose.yml down --volumes
    docker network rm gw_net > /dev/null 2>&1
else
    docker compose -f deploy/docker-compose.yml down
fi

if [[ -f "$STATE" ]]; then
    # Unload only what start.sh loaded, newest first.
    tac "$STATE" | while read -r module; do
        sudo modprobe -r "$module" || echo "Could not unload $module (in use?)" >&2
    done
    rm -f "$STATE"
fi
echo "Local environment stopped."
