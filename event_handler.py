#!/usr/bin/env python

import socket
import sys
import time
import os
import inspect
import importlib
import signal
import argparse
import json
import requests
import re
from baresip.netstring import Netstring

# Default Baresip host
baresipHost = "localhost"

signal.signal(signal.SIGINT, lambda:sys.exit(1))
signal.signal(signal.SIGTERM, lambda:sys.exit(1))

# parse arguments
args = sys.argv
parser = argparse.ArgumentParser(description='Event handler script')
parser.add_argument('-l','--log', help='Log file', required=False)
parser.add_argument('-a','--addr', help='Baresip IP', required=False)
parser.add_argument('-b','--browsing', help='Browsing file', required=True)
parser.add_argument('-r','--room', help='Room name', required=True)
parser.add_argument('-s','--res', help='Video resolution', required=True)
args = vars(parser.parse_args())

if args['log']:
    appLogs = open(args['log'], "a")
else:
    appLogs = sys.stdout

if args['addr']:
    baresipHost = args['addr']

# Get a browsing object from the browsing file name
sys.path.append(os.path.dirname(args['browsing']))

modName = os.path.splitext(os.path.basename(args['browsing']))[0]
print("Browsing mod name: "+modName, flush=True)

mod = importlib.import_module(modName)
isClassMember = lambda member: inspect.isclass(member) and member.__module__ == modName
browsingObj = inspect.getmembers(mod, isClassMember)[0][1]

dispWidth = args['res'].split('x')[0]
dispHeight = args['res'].split('x')[1]

browsing = []

# Event handler callback
def event_handler(data):
    global browsing
    print(data, flush=True)

    if data['type'] == 'CALL_ESTABLISHED':
        if 'peerdisplayname' in data:
            displayName = data['peerdisplayname']
        else:
            displayName = data['peeruri'].split(';')[0]

        browsing = browsingObj(args['room'], displayName, dispWidth, dispHeight)
        browsing.run()

    if data['type'] == 'CALL_CLOSED':
        browsing.stop()
        return 1

ns = Netstring(baresipHost, 4444)
# Start event handler loop
ns.getEvents(event_handler)

sys.exit(0)

