#!/usr/bin/env python

import socket
import sys
import json
import requests
import netstring as ns
import time

# ensure Baresip is launched and ready (do not remove !)
m = {"command":"uuid"}
while ns.sendCommand(m) == -1:
  ns.sendCommand(m)

# get network info 
m = {"command":"netstat"}
res = ns.sendCommand(m)
print(res[0]['data'])

# any others commands can be triggered here ...


# check baresip registering (do not remove !)
m = {"command":"uastat"}
res = ns.sendCommand(m)
if res[0]['data'].find('no user-agent') > -1:
  m = {"command":"quit"}
  res = ns.sendCommand(m)
  sys.exit(1)

sys.exit(0)






