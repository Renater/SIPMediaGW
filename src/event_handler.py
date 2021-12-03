#!/usr/bin/env python
import socket
import sys
import time
import os
import inspect
import subprocess
import importlib
import signal
import argparse
import json
import threading
from netstring import Netstring
from ivr import Ivr

# Default Baresip host
baresipHost = "localhost"

# Room number length
maxDigits = 10

# No active calls timeout (seconds)
noCallTo = 60

signal.signal(signal.SIGINT, lambda:sys.exit(1))
signal.signal(signal.SIGTERM, lambda:sys.exit(1))

# parse arguments
args = sys.argv
parser = argparse.ArgumentParser(description='Event handler script')
parser.add_argument('-l','--log', help='Log file', required=False)
parser.add_argument('-a','--addr', help='Baresip IP', required=False)
parser.add_argument('-b','--browsing', help='Browsing file', required=True)
parser.add_argument('-r','--room', help='Room name', required=False)
parser.add_argument('-f','--from', help='From URI', required=False)
parser.add_argument('-s','--res', help='Video resolution', required=True)
args = vars(parser.parse_args())

if args['log']:
    appLogs = open(args['log'], "a")
else:
    appLogs = sys.stdout

if args['addr']:
    baresipHost = args['addr']

if args['from']:
    print("From URI: "+args['from'], flush=True)

# Get a browsing object from the browsing file name
sys.path.append(os.path.dirname(args['browsing']))
modName = os.path.splitext(os.path.basename(args['browsing']))[0]
print("Browsing mod name: "+modName, flush=True)
mod = importlib.import_module(modName)
isClassMember = lambda member: inspect.isclass(member) and member.__module__ == modName
browsingObj = inspect.getmembers(mod, isClassMember)[0][1]

dispWidth = int(args['res'].split('x')[0])
dispHeight = int(args['res'].split('x')[1])

ivr = []
browsing = []

def browse(browsing):
    if browsing.run():
        subprocess.run(['echo "/quit" | netcat -q 1 127.0.0.1 5555'],
                       shell=True)

browsing = browsingObj(dispWidth, dispHeight, args['room'])

if not args['room']:
    ivr = Ivr("Entrez le numéro de la conférence",
              "ivr/ivr.png", "ivr/calibrii.ttf", 50)
    ivr.show(dispWidth,dispHeight,' *'*maxDigits)

# Event handler callback
def event_handler(data, browsing):
    if data['type'] == 'CALL_INCOMING':
        print(data, flush=True)
        if args['from'] and args['from'] != data['peeruri']:
            return {"command":"hangup"}
        else:
            return {"command":"accept"}

    if data['type'] == 'CALL_ESTABLISHED':
        print(data, flush=True)
        if 'peerdisplayname' in data:
            displayName = data['peerdisplayname']
        else:
            displayName = data['peeruri'].split(';')[0]

        browsing.name = displayName
        if browsing.room:
            browseThread = threading.Thread(target=browse, args=(browsing,))
            browseThread.start()
        else:
            subprocess.Popen(["sh","ivr_audio.sh"],
                             cwd='ivr',
                             stdin=subprocess.PIPE)

    if data['type'] == 'CALL_DTMF_START':
        if ivr and len(browsing.room) != maxDigits:
            print(data, flush=True)
            browsing.room = browsing.room + data['param']
            ivr.show(browsing.width, browsing.height, browsing.room)
            if len(browsing.room) == maxDigits:
                browseThread = threading.Thread(target=browse, args=(browsing,))
                browseThread.start()

    if data['type'] == 'CALL_CLOSED':
        if not args['from'] or \
           args['from'] and args['from'] == data['peeruri']:
            print(data, flush=True)
            return {"command":"quit"}

    # Time out expires before a CALL_ESTABLISHED
    if data['type'] == 'TIME_OUT' and not browsing.name:
        print(data, flush=True)
        return {"command":"quit"}

ns = Netstring(baresipHost, 4444)

# Start event handler loop
ns.getEvents(event_handler, browsing, noCallTo)

if ivr:
    ivr.close()
if browsing:
    browsing.stop()
subprocess.run(["xdotool", "key", "ctrl+W"])


sys.exit(0)

