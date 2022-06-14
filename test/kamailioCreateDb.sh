#!/bin/bash

touch `pwd`/kamailio.sqlite
docker run -it -v `pwd`/kamailio.sqlite:/usr/local/etc/kamailio/kamailio.sqlite  --entrypoint kamdbctl  kamailio  create
