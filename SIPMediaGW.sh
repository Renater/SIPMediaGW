#!/bin/bash

cleanup() {
    flock -u ${lockFd} > /dev/null 2>&1
}
trap cleanup SIGINT SIGQUIT SIGTERM

unset room prefix loop

while getopts r:f:p:l opt; do
    case $opt in
            r) room=$OPTARG ;;
            p) prefix=$OPTARG ;;
            l) loop=1 ;;
            *)
                echo 'Error in command line parsing' >&2
                exit 1
    esac
done

shift "$(( OPTIND - 1 ))"

CPU_PER_GW=${CPU_PER_GW:-2.5}

lockFilePrefix="sipmediagw"
gwNamePrefix="gw"

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
    timeOut=5
    timer=0
    state="$(docker container exec  $1  netstat -t | grep :4444 | grep -c ESTABLISHED)"
    while [[ ($state != "2") && ("$timer" < $timeOut) ]] ; do
        timer=$(($timer + 1))
        state="$(docker container exec  $1  netstat -t | grep :4444 | grep -c ESTABLISHED)"
        sleep 1
    done
    if [ "$timer" = $timeOut ]; then
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
if [[ "$loop" ]]; then
    restart="unless-stopped"
fi

### launch the gateway ###
gwName="gw"$id
RESTART=$restart \
HOST_TZ=$(cat /etc/timezone) \
ROOM=$room \
PREFIX=$prefix \
ID=$id \
docker compose -p ${gwName} up -d --force-recreate --remove-orphans gw

checkGwStatus $gwName
sipUri=$(docker container exec gw0  sh -c "cat /var/.baresip/accounts |
                                           sed 's/.*<//; s/;.*//'")
echo "{'res':'ok', 'uri':'$sipUri'}"

# child process => lockFile locked until the container exits:
ID=$id \
LOOP=$loop \
nohup bash -c 'state="$(docker wait gw$ID)"
               while [[ "$state" == "0" && $LOOP ]] ; do
                   state="$(docker wait gw$ID)"
               done' &> /dev/null &
