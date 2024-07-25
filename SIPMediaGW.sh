#!/bin/bash

cleanup() {
    flock -u ${lockFd} > /dev/null 2>&1
}
trap cleanup SIGINT SIGQUIT SIGTERM

unset room prefix loop

while getopts d:g:p:r:t:u:w:l opt; do
    case $opt in
            d) dial_uri=$OPTARG ;;
            g) gw_name=$OPTARG ;;
            p) prefix=$OPTARG ;;
            r) room=$OPTARG ;;
            t) timeout=$OPTARG ;;
            u) rtmp_dst=$OPTARG ;;
            w) webrtc_domain=$OPTARG ;;
            l) loop=1 ;;
            *)
                echo 'Error in command line parsing' >&2
                exit 1
    esac
done

shift "$(( OPTIND - 1 ))"

source <(grep = .env)

lockFilePrefix="sipmediagw"

lockGw() {
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
    # 5 seconds timeout before exit
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
check_reg="yes"
if [[ "$loop" && "$MAIN_APP" == "baresip" ]]; then
    restart="unless-stopped"
	check_reg="no"
fi

docker container prune --force > /dev/null

### launch the gateway ###
RESTART=$restart \
CHECK_REG=$check_reg \
HOST_TZ=$(cat /etc/timezone) \
ROOM=$room \
GW_NAME=$gw_name \
DOMAIN=$webrtc_domain \
RTMP_DST=$rtmp_dst \
PREFIX=$prefix \
ID=$id \
docker compose -p ${room:-"gw"$id} up -d --force-recreate --remove-orphans gw

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

# child process => lockFile locked until the container exits:
ID=$id \
LOOP=$loop \
nohup bash -c 'state="$(docker wait gw$ID)"
               while [[ "$state" == "0" && $LOOP ]] ; do
                   state="$(docker wait gw$ID)"
               done' &> /dev/null &
