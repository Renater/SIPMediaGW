#!/usr/bin/env python
import socket
import sys
import atexit
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

# Default Baresip host
baresipHost = "localhost"

def exit_handler():
    subprocess.run(['echo "/quit" | netcat -q 1 127.0.0.1 5555'],
             shell=True)

atexit.register(exit_handler)
signal.signal(signal.SIGTERM, exit_handler)
signal.signal(signal.SIGINT, exit_handler)

# parse arguments
inputs = sys.argv
parser = argparse.ArgumentParser(description='Event handler script')
parser.add_argument('-a','--addr', help='Baresip IP', required=False)
parser.add_argument('-b','--browsing', help='Browsing file', required=True)
parser.add_argument('-r','--room', help='Room name', required=False)
parser.add_argument('-f','--from', help='From URI', required=False)
parser.add_argument('-s','--res', help='Video resolution', required=True)
inputs = vars(parser.parse_args())

if inputs['addr']:
    baresipHost = inputs['addr']

if inputs['from']:
    print("From URI: "+inputs['from'], flush=True)

# Get a browsing object from the browsing file name
sys.path.append(os.path.dirname(inputs['browsing']))
modName = os.path.splitext(os.path.basename(inputs['browsing']))[0]
print("Browsing mod name: "+modName, flush=True)
mod = importlib.import_module(modName)
isClassMember = lambda member: inspect.isclass(member) and member.__module__ == modName
browsingObj = inspect.getmembers(mod, isClassMember)[0][1]

dispWidth = int(inputs['res'].split('x')[0])
dispHeight = int(inputs['res'].split('x')[1])

# Browsing
def browse(args):
    err = args['browsing'].run()
    exit_handler()

def endBrowse(args):
    if args['browsing']:
        args['browsing'].stop()
    subprocess.run(["xdotool", "key", "ctrl+W"])

# Event handler callback
def event_handler(data, args):
    if data['type'] == 'CALL_INCOMING':
        print(data, flush=True)
        if inputs['from'] and inputs['from'] != data['peeruri']:
            return {"command":"hangup"}
        else:
            return {"command":"accept"}

    if data['type'] == 'CALL_ESTABLISHED':
        print(data, flush=True)
        displayName = ''
        if 'peerdisplayname' in data:
            if not args['browsing'].room:
                # specific case with custom kamailio callflow
                try:
                    roomLen = int(data['peerdisplayname'].split('-', 1)[0])
                    args['browsing'].room = data['peerdisplayname'].split('-',1)[1][0:roomLen]
                    displayName = data['peerdisplayname'].split('-',1)[1][roomLen:]
                except:
                    displayName = data['peerdisplayname']
            else:
                displayName = data['peerdisplayname']
        if not displayName:
            displayName = data['peeruri'].split(';')[0].split(':')[1]
        print("My room: "+args['browsing'].room, flush=True)
        print("My name: "+displayName, flush=True)
        args['browsing'].name = displayName
        browseThread = threading.Thread(target=browse, args=(args,))
        browseThread.start()

    if data['type'] == 'CALL_DTMF_START':
        print('Received DTMF:'+ data['param'], flush=True)
        args['browsing'].userInputs.put(data['param'])

    if data['type'] == 'CALL_CLOSED':
        if (not inputs['from'] or
            inputs['from'] and inputs['from'] == data['peeruri']):
            print(data, flush=True)
            return {"command":"quit"}

    # Time out expires before a CALL_ESTABLISHED
    if data['type'] == 'TIME_OUT' and not args['browsing'].name:
        print(data, flush=True)
        return {"command":"quit"}


# Start event handler loop
ns = Netstring(baresipHost, 4444)

argDict = {'browsing':browsingObj(dispWidth, dispHeight, inputs['room'])}

ns.getEvents(event_handler, argDict)

# Terminate
endBrowse(argDict)

sys.exit(0)

