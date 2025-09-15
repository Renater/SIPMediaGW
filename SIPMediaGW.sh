#!/bin/bash
set -x

cleanup() {
    flock -u ${lockFd} > /dev/null 2>&1
}
trap cleanup SIGINT SIGQUIT SIGTERM

while [[ $# -gt 0 ]]; do
    case "$1" in
        -a|--main-app) main_app="$2"; shift 2;;
        -d|--dial-uri) dial_uri="$2"; shift 2;;
        -g|--gw-name) gw_name="$2"; shift 2;;
        -p|--prefix) prefix="$2"; shift 2;;
        -r|--room) room="$2"; shift 2;;
        -t|--timeout) timeout="$2"; shift 2;;
        -u|--rtmp-dst) rtmp_dst="$2"; shift 2;;
        -k|--api-key) api_key="$2"; shift 2;;
        -m|--recipient-mail) recipient_mail="$2"; shift 2;;
        -s|--with-transcript) with_transcript="true"; shift;;
        -w|--webrtc-domain) webrtc_domain="$2"; shift 2;;
        -l|--loop) loop=1; shift;;
        *)
            echo 'Error in command line parsing' >&2
            exit 1
    esac
done

shift "$(( OPTIND - 1 ))"

MAIN_APP=$(docker compose config 2>/dev/null | awk '/MAIN_APP:/ {print $2}')
MAIN_APP=${main_app:-$MAIN_APP}
CPU_PER_GW=$(docker compose config 2>/dev/null | awk '/CPU_PER_GW:/ {print $2}')

lockFilePrefix="sipmediagw"

lockGw() {
    CPU_PER_GW=$(echo "$CPU_PER_GW" | tr -d '"')
    maxGwNum=$(echo "$(nproc)/$CPU_PER_GW" | bc )
    i=0
    while [[ "$i" < $maxGwNum ]] ; do
        lockFile="/tmp/"${lockFilePrefix}$i".lock"
        exec {lockFd}>"/tmp/"${lockFilePrefix}$i".lock"
        flock -x -n $lockFd
        if [ "$?" == 0 ]; then
            id=$i
            break
        fi
        i=$(($i + 1))
    done
}

checkGwStatus() {
    # N seconds timeout before exit
    timeOut=$2
    timer=0
    state="$(docker container exec  $1  netstat -t | grep :4444 | grep -c ESTABLISHED)"
    while [[ ($state != "2") && ($timer -lt $timeOut) ]] ; do
        timer=$(($timer + 1))
        state="$(docker container exec  $1  netstat -t | grep :4444 | grep -c ESTABLISHED)"
        sleep 1
    done
    if [ $timer -eq $timeOut ]; then
        echo "{'res':'error','type':'The gateway failed to launch'}"
        exit 1
    fi
}

### get an ID and lock the corresponding file ###
lockGw

if [[ -z "$id" ]]; then
    echo "{'res':'error','type':'No free resources found'}"
    exit 1
fi

restart="no"
check_reg="no"
if [[ "$MAIN_APP" == "baresip" ]]; then
	if [[ "$loop" ]]; then
		restart="unless-stopped"
	else
		check_reg="yes"
	fi
fi

docker container prune --force > /dev/null
SERVICES="gw"
COMPOSE_FILE="-f docker-compose.yml"
if [[ "$with_transcript" ]]; then
	COMPOSE_FILE="$COMPOSE_FILE -f transcript/docker-compose.yml"
	ID=$id \
	SERVICES="$SERVICES transcript"
fi

### launch the gateway ###
MAIN_APP=$main_app \
RESTART=$restart \
CHECK_REG=$check_reg \
HOST_TZ=$(cat /etc/timezone) \
HOST_IP=${HOST_IP:-$(hostname -I | awk '{print $1}')} \
ROOM=$room \
GW_NAME=$gw_name \
DOMAIN=$webrtc_domain \
RTMP_DST=$rtmp_dst \
FS_API_KEY=$api_key \
FS_RECIPIENT_MAIL=$recipient_mail \
WITH_TRANSCRIPT=$with_transcript \
PREFIX=$prefix \
ID=$id \
docker compose -p ${room:-"gw"$id}  $COMPOSE_FILE up \
               -d --force-recreate --remove-orphans \
               $SERVICES

checkGwStatus "gw"$id ${timeout:-10}

MAIN_APP=$(docker exec gw0 sh -c 'echo $MAIN_APP')

if [ "$MAIN_APP" == "baresip" ]; then
    sipUri=$(docker exec gw$id sh -c 'cat /var/.baresip/accounts |
                                      sed "s/.*<//; s/;.*//"')
    echo "{'res':'ok', 'app': '$MAIN_APP', 'uri':'$sipUri'}"
    if [[ "$dial_uri" ]]; then
        gwIp=$(docker inspect -f \
                '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' \
                "gw"$id)
        echo '/dial '$dial_uri | netcat -q 1 $gwIp 5555
    fi
fi

if [ "$MAIN_APP" == "streaming" ]; then
    GW_PROXY=$(docker exec gw0 sh -c 'echo $GW_PROXY')
    echo "{'res':'ok', 'app': '$MAIN_APP', 'uri': '$rtmp_dst'}"
fi

if [ "$MAIN_APP" == "recording" ]; then
    echo "{'res':'ok', 'app': '$MAIN_APP', 'recipient mail': '$recipient_mail'}"
fi

# child process => lockFile locked until the container exits + recording post processing
ID=$id \
LOOP=$loop \
MAIN_APP=$MAIN_APP \
WITH_TRANSCRIPT=$with_transcript \
COMPOSE_FILE=$COMPOSE_FILE \
room=$room \
nohup bash -c 'state="$(docker wait gw$ID)"
               while [[ "$state" == "0" && $LOOP && "$MAIN_APP" == "baresip" ]] ; do
                   state="$(docker wait gw$ID)"
               done
               if [[ "$MAIN_APP" == "recording" ]]; then
                   if [[ "$WITH_TRANSCRIPT" ]]; then
                       ID=$ID \
                       docker compose -p $room  $COMPOSE_FILE up -d \
                       --force-recreate --remove-orphans transcript
                   fi
                   docker restart gw$ID
                   docker wait gw$ID
                   docker stop transcript$ID
               fi' &> /dev/null &
