#!/bin/bash

exit | mysql -h 127.0.0.1 -P 3306 -u root -p$MYSQL_ROOT_PASSWORD
