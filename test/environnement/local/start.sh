#!/bin/bash
# Start a local SIPMediaGW test environment on this host: Kamailio, TURN,
# MySQL and one gateway (gw0), ready to receive a SIP call.
#
#   BROWSING=jitsi DOCKER_IMAGE=sipmediagw:dev ./start.sh
#
# Optional: HOST_IP (auto-detected), RTCSTATS_SERVER_URL (enables rtcstats).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
STATE=/tmp/sipmediagw-local.state
cd "$ROOT"

export BROWSING=${BROWSING-jitsi}
export DOCKER_IMAGE=${DOCKER_IMAGE:-sipmediagw:dev}
# The address that routes to the internet, not docker0 (hostname -I lists it first).
export HOST_IP=${HOST_IP:-$(ip route get 1.1.1.1 | awk '{for(i=1;i<=NF;i++) if($i=="src") {print $(i+1); exit}}')}
[[ -n "$HOST_IP" ]] || { echo "Cannot detect HOST_IP, set it explicitly." >&2; exit 1; }

docker network inspect gw_net > /dev/null 2>&1 ||
    docker network create --subnet=192.168.92.0/29 gw_net > /dev/null
# gw0 sits on gw_net, where 127.0.0.1 is the container itself: a loopback
# HOST_IP becomes the gw_net gateway, a host address that gw0 can reach.
if [[ "$HOST_IP" == 127.* || "$HOST_IP" == localhost ]]; then
    HOST_IP=$(docker network inspect -f '{{(index .IPAM.Config 0).Gateway}}' gw_net)
    echo "Loopback HOST_IP is unreachable from gw0, using the gw_net gateway instead."
fi
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
export ROOM="" PREFIX="" INIT="" RTMP_DST="" FS_API_KEY="" FS_USER_MAIL="" FS_RECIPIENT_MAIL="" \
       WITH_TRANSCRIPT="" PULSE_SERVER=""
if [[ -n "${RTCSTATS_SERVER_URL:-}" ]]; then
    export RTCSTATS_ENABLED=true RTCSTATS_SERVER_URL
fi
docker compose -p localgw up -d --force-recreate gw
echo -n "Waiting for gw0 "
for _ in $(seq 60); do
    [[ "$(docker exec gw0 netstat -t 2>/dev/null | grep :4444 | grep -c ESTABLISHED)" == 2 ]] && break
    echo -n .; sleep 1
done
[[ "$(docker exec gw0 netstat -t 2>/dev/null | grep :4444 | grep -c ESTABLISHED)" == 2 ]] ||
    { echo " gateway failed to start (journalctl | grep gw0)" >&2; exit 1; }
echo " ok"

cat <<EOF

Ready. From a SIP softphone (Linphone: no registration, no ICE/AVPF, TCP),
call one of:
    sip:<room>@$HOST_IP      join <room> on ${BROWSING:-the platform chosen in the IVR}
    sip:0@$HOST_IP           IVR
Logs:   journalctl -f | grep -E 'gw0|kamailio'
Stop:   $(dirname "${BASH_SOURCE[0]}")/stop.sh
EOF
