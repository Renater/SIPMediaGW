#!/bin/bash

cleanup() {
    flock -u ${lockFd} > /dev/null 2>&1
}
trap cleanup SIGINT SIGQUIT SIGTERM
init=''
while [[ $# -gt 0 ]]; do
    case "$1" in
        -a|--main-app) main_app="$2"; shift 2;;
        -b|--browsing-name) browsing_name="$2"; shift 2;;
        -d|--dial-uri) dial_uri="$2"; shift 2;;
        -g|--gw-name) gw_name="$2"; shift 2;;
        -p|--prefix) prefix="$2"; shift 2;;
        -r|--room) room="$2"; shift 2;;
        -t|--timeout) timeout="$2"; shift 2;;
        -u|--rtmp-dst) rtmp_dst="$2"; shift 2;;
        -k|--api-key) api_key="$2"; shift 2;;
        -m|--recipient-mail) recipient_mail="$2"; shift 2;;
        -n|--user-name) user_name="$2"; shift 2;;
        -o|--audio-only) audio_only="true"; shift 2;;
        -s|--with-transcript) with_transcript="true"; shift;;
        -l|--loop) loop=1; shift;;
        -i|--init) init=1; shift;;
        -x|--display) display="$2"; shift 2;;
        *)
            echo 'Error in command line parsing' >&2
            exit 1
    esac
done

shift "$(( OPTIND - 1 ))"

MAIN_APP=$(docker compose config 2>/dev/null | awk '/MAIN_APP:/ {print $2}')
MAIN_APP=${main_app:-$MAIN_APP}
FS_API_KEY=${api_key:-$FS_API_KEY}

CPU_PER_GW=$(docker compose config 2>/dev/null | awk '/CPU_PER_GW:/ {print $2}')

if [[ -n "$display" ]]; then
    DISPLAY=:$display xhost +local:docker
    pulse_server=unix:/tmp/pulse/native
    with_alsa="false"
fi

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

# If gw_name is provided use it to get the ID
if [[ -n $gw_name ]]; then
    id=$(docker compose -p $gw_name ps -a --format '{{json .Name}}'| tr -cd '0-9')
else
    lockGw
fi

if [[ -z "$id" ]]; then
    CPU_PER_GW=$(echo "$CPU_PER_GW" | tr -d '"')
    maxGwNum=$(echo "$(nproc)/$CPU_PER_GW" | bc )
    if [ -e "/tmp/${lockFilePrefix}$(($maxGwNum - 1)).lock" ]; then
        echo "{'res':'error','type':'All gateways were started : $maxGwNum'}"
        exit 1
    else
        echo "{'res':'error','type':'No resources available to start the gateway'}"
        exit 1
    fi
fi

restart="no"
check_reg="no"
video_dev="null"
if [[ "$MAIN_APP" == "baresip" ]]; then
	if [[ "$loop" ]]; then
		restart="unless-stopped"
	else
		check_reg="yes"
	fi
    if [ "$audio_only" != "true" ]; then
        video_dev="video$id"
    fi
fi
if [[ -n "$display" ]]; then
    video_dev="video$id"
fi

if [[ -n "$init" || ( "$MAIN_APP" == "baresip" ) ]]; then
    docker container rm gw$id --force > /dev/null
fi

SERVICES="gw"
COMPOSE_FILE="-f docker-compose.yml"
if [[ "$with_transcript" ]]; then
	COMPOSE_FILE="$COMPOSE_FILE -f transcript/docker-compose.yml"
	SERVICES="$SERVICES transcript"
fi
if [[ "$display" ]]; then
	COMPOSE_FILE="$COMPOSE_FILE -f x11/docker-compose.yml"
fi

if [[ -z "$gw_name" ]]; then
    GW_NAME=$(tr -dc 'a-z0-9' </dev/urandom | head -c 24)
else
    GW_NAME=$gw_name
fi

### launch the gateway ###

MAIN_APP=$MAIN_APP \
RESTART=$restart \
CHECK_REG=$check_reg \
HOST_TZ=$(cat /etc/timezone) \
HOST_IP=${HOST_IP:-$(hostname -I | awk '{print $1}')} \
ROOM=$room \
GW_NAME=$GW_NAME \
BROWSING=$browsing_name \
RTMP_DST=$rtmp_dst \
FS_API_KEY=$FS_API_KEY \
FS_RECIPIENT_MAIL=$recipient_mail \
WITH_TRANSCRIPT=$with_transcript \
PREFIX=$prefix \
ID=$id \
INIT=$init \
AUDIO_ONLY=$audio_only \
VIDEO_DEV=$video_dev \
DISPLAY=$DISPLAY \
DISPLAY=${display:+:$display} \
PULSE_SERVER=$pulse_server \
WITH_ALSA=$with_alsa \
USER=$user_name \
docker compose -p ${GW_NAME:-"gw"$id} $COMPOSE_FILE up \
               -d --force-recreate  \
               $SERVICES

if [ "$MAIN_APP" == "baresip" ]; then
    checkGwStatus "gw"$id ${timeout:-10}
fi

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
    echo "{'res':'ok', 'app': '$MAIN_APP', 'uri': '$rtmp_dst'}"
fi

if [ "$MAIN_APP" == "recording" ]; then
    echo "{'res':'ok', 'app': '$MAIN_APP', 'recipient mail': '$recipient_mail'}"
fi


# Wait for init mode
if [[  "$init"  &&  "$MAIN_APP" != "baresip" ]]; then
    nohup bash -c "docker wait gw$id" &> /dev/null &
else 
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
                        docker compose -p $GW_NAME $COMPOSE_FILE up -d \
                        --force-recreate transcript
                    fi
                    docker restart gw$ID
                    docker wait gw$ID
                    docker stop transcript$ID
                fi' &> /dev/null &
fi