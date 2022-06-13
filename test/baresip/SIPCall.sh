#!/bin/bash

unset dial

while getopts d: opt; do
    case $opt in
            d) dial=$OPTARG ;;
            *)
                echo 'Error in command line parsing' >&2
                exit 1
    esac
done

DIAL="-e d"${dial} \
docker compose run baresip
