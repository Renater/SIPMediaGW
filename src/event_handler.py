#!/usr/bin/env python
import socket
import sys
import atexit
import time
import psutil
import os
import inspect
import subprocess
import importlib
import signal
import argparse
import json
import threading
from ivr import IVR
from netstring import Netstring

# Default Baresip host
baresipHost = "localhost"

def isFfmpegRunning():
    """At least on ffmpeg is actif and not zombie"""
    for proc in psutil.process_iter(attrs=['name', 'status']):
        if proc.info['name'] == "ffmpeg" and proc.info['status'] not in ["zombie", "stopped"]:
            return True
    return False

def exit_handler():
    print("Cleaning up...")
    subprocess.run(['echo "/quit" | netcat -q 1 127.0.0.1 5555'], shell=True)
    os.system("killall -SIGINT ffmpeg")
    while isFfmpegRunning():
        print("FFmpeg still running...")
        time.sleep(1)

atexit.register(exit_handler)
signal.signal(signal.SIGTERM, exit_handler)
signal.signal(signal.SIGINT, exit_handler)

# parse arguments
parser = argparse.ArgumentParser(description='Event handler script')
parser.add_argument('-a','--addr', help='Baresip IP', required=False)
parser.add_argument('-r','--room', help='Room name', required=False)
parser.add_argument('-f','--from', help='From URI', required=False)
parser.add_argument('-s','--res', help='Video resolution', required=True)
inputs = vars(parser.parse_args())

if inputs['addr']:
    baresipHost = inputs['addr']

if inputs['from']:
    print("From URI: "+inputs['from'], flush=True)

dispWidth = int(inputs['res'].split('x')[0])
dispHeight = int(inputs['res'].split('x')[1])

# instanciate IVR
ivr = IVR(
    width=dispWidth,
    height=dispHeight,
    roomName=inputs.get('room', ''),
    name='',
    browsingName=os.environ.get('BROWSING')
)

def browse(args):
    args['ivr'].run()
    subprocess.run(['echo "/hangup" | netcat -q 1 127.0.0.1 5555'], shell=True)

def endBrowse(args):
    if args['ivr'] and args['ivr'].browsingObj:
        args['ivr'].browsingObj.stop()
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
            try:
                if args['ivr'].roomName:
                    print("Static room name (may be overwritten => ivr.js): "+args['ivr'].roomName, flush=True)
                roomLen = int(data['peerdisplayname'].split('-', 1)[0])
                args['ivr'].mixedId = data['peerdisplayname'].split('-',1)[1][0:roomLen]
                print("Call prefix: "+args['ivr'].mixedId, flush=True)
                displayName = data['peerdisplayname'].split('-',1)[1][roomLen:]
            except:
                displayName = data['peerdisplayname']
        if not displayName:
            displayName = data['peeruri'].split(';')[0].split(':')[1]
        print("My name: "+displayName, flush=True)
        args['ivr'].name = displayName
        browseThread = threading.Thread(target=browse, daemon=True, args=(args,))
        browseThread.start()

    if data['type'] == 'CALL_DTMF_START':
        print('Received DTMF:'+ data['param'], flush=True)
        args['ivr'].userInputs.put(data['param'])

    if data['type'] == 'CALL_CLOSED':
        if (not inputs['from'] or
            inputs['from'] and inputs['from'] == data['peeruri']):
            print(data, flush=True)
            return {"command":"quit"}

    # Time out expires before a CALL_ESTABLISHED
    if data['type'] == 'TIME_OUT' and not args['ivr'].name:
        print(data, flush=True)
        return {"command":"quit"}

    if data['type'] == 'VIDEO_DISP':
        print(data, flush=True)
        if data['param'] == 'VIDEO_SLIDES_START':
            args['ivr'].userInputs.put('s')
            args['ivr'].screenShared = True
        if (data['param'] == 'VIDEO_SLIDES_STOP' and
            args['ivr'].screenShared == True):
            args['ivr'].userInputs.put('s')
            args['ivr'].screenShared = False

    if data['type'] == 'CHAT_INPUT':
        if 'text' in data:
            print('Received chat message: '+ data['text'], flush=True)
            args['ivr'].browsingObj.chatMsg.put(data['text'])
        if 'action' in data:
            print('Received chat action: '+ data['action'], flush=True)
            if data['action'] == 'toggle':
                args['ivr'].userInputs.put('c')

argDict = {'ivr': ivr}

if os.environ.get('MAIN_APP') != 'baresip':
    argDict['ivr'].name = os.environ.get('MAIN_APP')
    browseThread = threading.Thread(target=browse, args=(argDict,))
    browseThread.start()

# Start event handler loop
ns = Netstring(baresipHost, 4444)
ns.getEvents(event_handler, argDict)

# Terminate
endBrowse(argDict)

sys.exit(0)

