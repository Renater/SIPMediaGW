#!/bin/bash

touch `pwd`/kamailio.sqlite
docker run -it -v `pwd`/kamailio.sqlite:/usr/local/etc/kamailio/kamailio.sqlite -v `pwd`/kamailio:/etc/kamailio:ro --entrypoint kamdbctl  kamailio  create
docker run -it -v `pwd`/kamailio.sqlite:/usr/local/etc/kamailio/kamailio.sqlite -v `pwd`/kamailio:/etc/kamailio:ro --entrypoint  sqlite3  kamailio /usr/local/etc/kamailio/kamailio.sqlite "alter table location add column last_locked TIMESTAMP WITHOUT TIME ZONE NOT NULL DEFAULT '2000-01-01 00:00:01'"
