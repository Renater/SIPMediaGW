#!/bin/bash
# Start a local SIPMediaGW test environment on this host: Kamailio, TURN,
# MySQL and one gateway (gw0), ready to receive a SIP call.
#
#   BROWSING=jitsi DOCKER_IMAGE=sipmediagw:dev ./start.sh
#
# Optional: HOST_IP (auto-detected), RTCSTATS_SERVER_URL (enables rtcstats),
# LOOP=0 (do not recreate gw0 after each call).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
STATE=/tmp/sipmediagw-local.state
LOOP_PID=/tmp/sipmediagw-local.loop.pid
LOOP_LOG=/tmp/sipmediagw-local.loop.log
cd "$ROOT"

export BROWSING=${BROWSING-jitsi}
export DOCKER_IMAGE=${DOCKER_IMAGE:-sipmediagw:dev}
# The address a softphone on this host advertises in its SDP: the one that
# routes to the internet (not docker0, which hostname -I lists first).
DEFAULT_IP=$(ip route get 1.1.1.1 | awk '{for(i=1;i<=NF;i++) if($i=="src") {print $(i+1); exit}}')
export HOST_IP=${HOST_IP:-$DEFAULT_IP}
# 127.0.0.1 inside gw0 is the container itself. Another host address (e.g. the
# gw_net gateway) gets signalling through but not media: TURN only relays
# from the address Linphone advertises, while Linphone sends from the address
# it targets. So a loopback HOST_IP becomes that advertised address.
if [[ "$HOST_IP" == 127.* || "$HOST_IP" == localhost ]]; then
    echo "Loopback HOST_IP is unreachable from gw0, using $DEFAULT_IP instead."
    HOST_IP=$DEFAULT_IP
fi
[[ -n "$HOST_IP" ]] || { echo "Cannot detect HOST_IP, set it explicitly." >&2; exit 1; }

docker network inspect gw_net > /dev/null 2>&1 ||
    docker network create --subnet=192.168.92.0/29 gw_net > /dev/null
echo "HOST_IP=$HOST_IP  BROWSING=${BROWSING:-<IVR>}  DOCKER_IMAGE=$DOCKER_IMAGE"

### Kernel modules ###
# The gateway uses two ALSA loopback cards (Loopback, Loopback_1) for gw0.
if [[ ! -d /sys/module/snd_aloop ]]; then
    sudo modprobe snd-aloop enable=1,1
    echo snd-aloop >> "$STATE"
fi
# Loopback video devices numbered from 10 so they never collide with webcams.
if [[ ! -d /sys/module/v4l2loopback ]]; then
    sudo modprobe v4l2loopback devices=1 video_nr=10 exclusive_caps=1
    echo v4l2loopback >> "$STATE"
fi
VIDEO_DEV=$(ls /sys/devices/virtual/video4linux 2>/dev/null | sort -V | head -1)
[[ -n "$VIDEO_DEV" ]] || { echo "No v4l2loopback device found." >&2; exit 1; }

### Images ###
docker image inspect kamailio4sipmediagw > /dev/null 2>&1 ||
    docker build -t kamailio4sipmediagw deploy/kamailio
docker image inspect coturn4sipmediagw > /dev/null 2>&1 ||
    docker build -t coturn4sipmediagw deploy/coturn
docker image inspect "$DOCKER_IMAGE" > /dev/null 2>&1 ||
    docker build --build-arg ALLOW_DEV_BUILD=1 -t "$DOCKER_IMAGE" .

### SIP server, TURN, database ###
docker compose -f deploy/docker-compose.yml up -d sip_db sip_server turn_server
echo -n "Waiting for Kamailio on $HOST_IP:5060 "
for _ in $(seq 60); do
    ss -ltn | grep -q "$HOST_IP:5060 " && break
    echo -n .; sleep 2
done
ss -ltn | grep -q "$HOST_IP:5060 " || { echo " timeout (journalctl -t kamailio)" >&2; exit 1; }
echo " ok"

### Gateway gw0 ###
HOST_TZ=$(cat /etc/timezone 2>/dev/null || timedatectl show -p Timezone --value)
export ID=0 GW_NAME=localgw MAIN_APP=baresip VIDEO_DEV HOST_TZ \
       CHECK_REG=yes RESTART=no WITH_ALSA=true
# The rest of what SIPMediaGW.sh exports, empty here: keeps compose quiet.
# DISPLAY too: the desktop's DISPLAY would make gw0 skip its own Xvfb and
# look for the host's X server, which is not shared (SIPMediaGW.sh -d does).
export DISPLAY="" ROOM="" PREFIX="" INIT="" RTMP_DST="" FS_API_KEY="" FS_USER_MAIL="" FS_RECIPIENT_MAIL="" \
       WITH_TRANSCRIPT="" PULSE_SERVER=""
if [[ -n "${RTCSTATS_SERVER_URL:-}" ]]; then
    export RTCSTATS_ENABLED=true RTCSTATS_SERVER_URL
fi
# A watcher left by a previous run would recreate gw0 behind our back.
[[ -f "$LOOP_PID" ]] && { kill -- -"$(cat "$LOOP_PID")" 2> /dev/null || true; }
rm -f "$LOOP_PID"
docker compose -p localgw up -d --force-recreate gw
echo -n "Waiting for gw0 "
for _ in $(seq 60); do
    [[ "$(docker exec gw0 netstat -t 2>/dev/null | grep :4444 | grep -c ESTABLISHED)" == 2 ]] && break
    echo -n .; sleep 1
done
[[ "$(docker exec gw0 netstat -t 2>/dev/null | grep :4444 | grep -c ESTABLISHED)" == 2 ]] ||
    { echo " gateway failed to start (journalctl | grep gw0)" >&2; exit 1; }
echo " ok"

# gw0 exits at the end of each call: recreate it, as SIPMediaGW.sh --loop does.
# Own session (setsid) so stop.sh can kill the watcher and docker events at once.
if [[ "${LOOP:-1}" == 1 ]]; then
    setsid bash -c 'docker events --filter container=gw0 --filter event=die |
        while read -r _; do
            echo "$(date +%T) gw0 exited, recreating it"
            sleep 2
            docker compose -p localgw up -d --force-recreate gw
        done' > "$LOOP_LOG" 2>&1 < /dev/null &
    echo $! > "$LOOP_PID"
fi

cat <<EOF

Ready. From a SIP softphone (Linphone: no registration, no ICE/AVPF, TCP),
call one of:
    sip:<room>@$HOST_IP      join <room> on ${BROWSING:-the platform chosen in the IVR}
    sip:0@$HOST_IP           IVR
Logs:   journalctl -f | grep -E 'gw0|kamailio'
Loop:   gw0 is recreated after each call (LOOP=0 to disable): $LOOP_LOG
Stop:   $(dirname "${BASH_SOURCE[0]}")/stop.sh
EOF
