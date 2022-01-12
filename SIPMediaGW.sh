#!/bin/bash

cleanup() {
    flock -u ${lock_fd} > /dev/null 2>&1
    rm -f ${lock_file} > /dev/null 2>&1
}
trap cleanup SIGINT SIGQUIT SIGTERM EXIT

unset room
unset from
accounts_file="baresip/accounts"

while getopts r:f:a: opt; do
    case $opt in
            r) room=$OPTARG ;;
            f) from=$OPTARG ;;
            a) accounts_file=$OPTARG ;;
            *)
                echo 'Error in command line parsing' >&2
                exit 1
    esac
done

shift "$(( OPTIND - 1 ))"

if [ ! -f $accounts_file ]; then
        echo 'Accounts file: '$accounts_file' does not exist' >&2
        exit 1
fi

sip_account=''
lock_file_prefix="sipmediagw"
gwNamePrefix="gw"

find_free_id() {
    accounts_data=`cat $accounts_file`
    accounts="$(echo "$accounts_data" | sed -e '/^\s*#.*$/d' -e '/^\s*$/d')"
    i=0
    while IFS= read -r line && [ -n "$accounts" ]
    do
        lock_file="/tmp/"${lock_file_prefix}$i".lock"
        exec {lock_fd}>"/tmp/"${lock_file_prefix}$i".lock"
        flock -x -n $lock_fd
        if [ "$?" == 0 ]; then
            docker container exec  $gwNamePrefix$i echo > /dev/null 2>&1
            if [ "$?" == 1 ]; then
                id=$i
                sip_account=$line
                break
            else
                cleanup # => unlock
            fi
        fi
        i=$(($i + 1))
    done <<< "$accounts"
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
        echo "{'res':'error','type':'The gateway failed to launch'}"
        exit 1
    fi
}

### get an ID and lock the corresponding file ###
find_free_id

if [[ -z "$id" ]]; then
    echo "{'res':'error','type':'No free ressources/accounts found'}"
    exit 1
fi

### launch the gateway ###
gwName="gw"$id
HOST_TZ=$(cat /etc/timezone) \
ROOM=$room FROM=$from \
ACCOUNT=$sip_account \
ID=$id \
docker-compose -p $gwName up -d --force-recreate --remove-orphans gw

check_gw_status $gwName
sip_uri=$(awk -F'<|;' '{print $2}' <<< $sip_account)
echo "{'res':'ok', 'uri':'$sip_uri'}"

