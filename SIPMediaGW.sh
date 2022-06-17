#!/bin/bash

cleanup() {
    flock -u ${lockFd} > /dev/null 2>&1
    rm -f ${lockFile} > /dev/null 2>&1
}
trap cleanup SIGINT SIGQUIT SIGTERM EXIT

unset room
unset from
unset prefix

while getopts r:f:p: opt; do
    case $opt in
            r) room=$OPTARG ;;
            f) from=$OPTARG ;;
            p) prefix=$OPTARG ;;
            *)
                echo 'Error in command line parsing' >&2
                exit 1
    esac
done

shift "$(( OPTIND - 1 ))"

source <(grep = sipmediagw.cfg)

lockFilePrefix="sipmediagw"
gwNamePrefix="gw"

find_free_id() {
    maxGwNum=$(echo "$(nproc)/$cpuCorePerGw" | bc )
    i=0
    while [[ "$i" < $maxGwNum ]] ; do
        lockFile="/tmp/"${lockFilePrefix}$i".lock"
        exec {lockFd}>"/tmp/"${lockFilePrefix}$i".lock"
        flock -x -n $lockFd
        if [ "$?" == 0 ]; then
            docker container exec  $gwNamePrefix$i echo > /dev/null 2>&1
            if [ "$?" == 1 ]; then
                id=$i
                break
            else
                cleanup # => unlock
            fi
        fi
        i=$(($i + 1))
    done
}

check_gw_status() {
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
        echo "{'res':'error','type':'The gateway failed to launch', 'data': '$sipAccount'}"
        exit 1
    fi
}

### get an ID and lock the corresponding file ###
find_free_id

if [[ -z "$id" ]]; then
    echo "{'res':'error','type':'No free resources found'}"
    exit 1
fi

### set SIP account ###
userNamePref=${sipUaNamePart}"."${id}
if [[ "$prefix" ]]; then
    userNamePref=${prefix}"."${userNamePref}
fi
sipAccount="<sip:"${userNamePref}"@"${sipSrv}";transport=tcp>;regint=60;"
sipAccount+="auth_user="${userNamePref}";auth_pass="${sipSecret}";"
sipAccount+="medianat=turn;stunserver="${turnConfig}

### launch the gateway ###
gwName="gw"$id
HOST_TZ=$(cat /etc/timezone) \
ACCOUNT=$sipAccount \
ID=$id \
docker compose -p $gwName up -d --force-recreate --remove-orphans gw

check_gw_status $gwName
sipUri=$(awk -F'<|;' '{print $2}' <<< $sipAccount)
echo "{'res':'ok', 'uri':'$sipUri'}"

