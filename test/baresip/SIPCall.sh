#!/bin/bash

xhost +local:docker

path=$(dirname "${BASH_SOURCE[0]}")
dial=""

while getopts d:u: opt; do
    case $opt in
            d) dial=$OPTARG ;;
            u) ua=$OPTARG ;;
            *)
                echo 'Error in command line parsing' >&2
                exit 1
    esac
done

if [[ "$ua" ]]; then
    ua="-e '/uafind ${ua}'"
fi

if [[ "$dial" ]]; then
    dial="-e d"${dial}
fi

UA=$ua \
DIAL=$dial \
docker compose -f $path"/docker-compose.yml" run --rm baresip
