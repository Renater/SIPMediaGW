#!/bin/bash

dial=""

while getopts d: opt; do
    case $opt in
            d) dial=$OPTARG ;;
            *)
                echo 'Error in command line parsing' >&2
                exit 1
    esac
done

if [[ "$dial" ]]; then
    dial="-e d"${dial}
fi

DIAL=$dial \
docker compose run --name baresip --rm baresip
