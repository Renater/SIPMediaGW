#!/bin/bash

cleanup() {
    flock -u ${lock_fd} > /dev/null 2>&1
    rm -f ${lock_file} > /dev/null 2>&1
    exit 1
}
trap cleanup SIGINT SIGQUIT SIGTERM EXIT

unset room
unset gateway_name
accounts_file="baresip/accounts"

while getopts r:g:a: opt; do
    case $opt in
            r) room=$OPTARG ;;
            g) gateway_name=$OPTARG ;;
            a) accounts_file=$OPTARG ;;
            *)
                echo 'Error in command line parsing' >&2
                exit 1
    esac
done

shift "$(( OPTIND - 1 ))"

if [ -z "$room" ] || [ -z "$gateway_name" ]; then
        echo 'Missing -r or -g' >&2
        exit 1
fi

if [ ! -f $accounts_file ]; then
        echo 'Accounts file: '$accounts_file' does not exist' >&2
        exit 1
fi

sip_account=''
lock_file_prefix="sipmediagw"

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
            id=$i
            sip_account=$line
            break
        fi
        i=$(($i + 1))
    done <<< "$accounts"
}

### get an ID and lock the corresponding file ###
find_free_id

if [[ -z "$id" ]]; then
    echo "No free ressources/accounts found"
    exit 1
fi

room_name=$(echo $room | sed -u 's/\///')
logPref="logs/SIPWG"$id"_"$room_name

### launch the gateway ###
HOST_TZ=$(cat /etc/timezone) \
ROOM=$room ID=$id ACCOUNT=$sip_account LOGS=$logPref \
docker-compose -p $gateway_name up --force-recreate

