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
from baresip.netstring import Netstring
from ivr.ivr import Ivr


# Default Baresip host
baresipHost = "localhost"

# Room number length
maxDigits = 4

# SIP connection timeout (seconds)
sipTo = 60

signal.signal(signal.SIGINT, lambda:sys.exit(1))
signal.signal(signal.SIGTERM, lambda:sys.exit(1))

def timeout ():
    nsTo = Netstring(baresipHost, 4444)
    m = {"command":"callstat"}
    while True:
        time.sleep (sipTo)
        res = nsTo.sendCommand(m)
        if not (res !=-1 and res[0]['response']==True and \
                res[0]['data'].find("(no active calls)") == -1 ):
           # Quit baresip if "no active calls"
           m = {"command":"quit"}
           res = nsTo.sendCommand(m)
           break


# parse arguments
args = sys.argv
parser = argparse.ArgumentParser(description='Event handler script')
parser.add_argument('-l','--log', help='Log file', required=False)
parser.add_argument('-a','--addr', help='Baresip IP', required=False)
parser.add_argument('-b','--browsing', help='Browsing file', required=True)
parser.add_argument('-r','--room', help='Room name', required=False)
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

dispWidth = int(args['res'].split('x')[0])
dispHeight = int(args['res'].split('x')[1])

ivr = []
browsing = []
ivrAuProc = []
browseThread = []

browsing = browsingObj(dispWidth, dispHeight, args['room'])
browseThread = threading.Thread(target=browsing.run)

if not args['room']:
    ivr = Ivr("Entrez le numéro de la conférence",
              "ivr/ivr.png", "ivr/calibrii.ttf", 50)
    ivr.show(dispWidth,dispHeight,'* * * *')
    roomName = ''

toThread = threading.Thread(target=timeout)
toThread.start()

# Event handler callback
def event_handler(data):
    global browsing, ivrAuProc, roomName, ivr, \
           browseThread, dispWidth, dispHeight

    if data['type'] == 'CALL_ESTABLISHED':
        print(data, flush=True)
        if 'peerdisplayname' in data:
            displayName = data['peerdisplayname']
        else:
            displayName = data['peeruri'].split(';')[0]

        browsing.name = displayName
        if browsing.room:
            browseThread.start()
        else:
            ivrAuProc = subprocess.Popen(["sh","ivr_audio.sh"],
                                          cwd='ivr',
                                          stdin=subprocess.PIPE)

    if data['type'] == 'CALL_DTMF_START':
        roomName = roomName + data['param']
        ivr.show(dispWidth,dispHeight, roomName)
        if len(roomName) == maxDigits:
            browsing.room = roomName
            browseThread.start()
            roomName = ''

    if data['type'] == 'CALL_CLOSED':
        print(data, flush=True)
        if ivr:
            ivr.close()
        browsing.stop()
        subprocess.run(["xdotool", "key", "ctrl+W"])
        return 1

ns = Netstring(baresipHost, 4444)
# Start event handler loop
ns.getEvents(event_handler)

sys.exit(0)

