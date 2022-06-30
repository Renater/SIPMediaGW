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

signal.signal(signal.SIGTERM,
              lambda s,f:
              subprocess.run(['echo "/quit" | netcat -q 1 127.0.0.1 5555'],
                             shell=True))

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

# IVR
class IvrBis(Ivr):
    def __init__(self, prompt, bgFile, fontFile, fontsize):
        Ivr.__init__(self, prompt, bgFile, fontFile, fontsize)
        self.trial = 0
    def onTimeout(self):
        print("IVR Timeout", flush=True)
        subprocess.run(['echo "/quit" | netcat -q 1 127.0.0.1 5555'],
                       shell=True)

def getIvr():
    ivr = IvrBis("Entrez le numéro de la conférence",
                           "ivr/ivr.png", "ivr/calibrii.ttf", 50)
    ivr.maxDelay = 120 #seconds
    ivr.show(dispWidth,dispHeight,'')
    return ivr

def startIvr(ivr):
    if ivr:
        ivr.trial+= 1
        ivr.show(dispWidth,dispHeight,' *'*maxDigits)
        auProc = subprocess.Popen(["sh","ivr_audio.sh"],
                                  cwd='ivr',
                                  stdin=subprocess.PIPE)
    else:
        print("IVR not set", flush=True)

# Browsing
def browse(args):

    args['browse_lock'].acquire()

    err = args['browsing'].run()
    args['browse_error'] = bool(err)

    if err:
        args['browsing'].room=''

        if  args['ivr']:
            if args['ivr'].trial >= 3:
                subprocess.run(['echo "/quit" | netcat -q 1 127.0.0.1 5555'],
                               shell=True)
            args['ivr'].trial+= 1
            auProc = subprocess.Popen(["sh","ivr_audio.sh"],
                                      cwd='ivr',
                                      stdin=subprocess.PIPE)
    else:
        if args['ivr']:
            args['ivr'].close()

    args['browse_lock'].release()

def endBrowse(args):
    if args['ivr']:
        args['ivr'].close()
    if args['browsing']:
        args['browsing'].stop()
    subprocess.run(["xdotool", "key", "ctrl+W"])

# Event handler callback
def event_handler(data, args):

    if args['browse_error'] and not args['ivr']:
        args['ivr'] = getIvr()
        startIvr(args['ivr'])

    if data['type'] == 'CALL_INCOMING':
        print(data, flush=True)
        if inputs['from'] and inputs['from'] != data['peeruri']:
            return {"command":"hangup"}
        else:
            return {"command":"accept"}

    if data['type'] == 'CALL_ESTABLISHED':
        print(data, flush=True)
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
        if args['browsing'].room:
            browseThread = threading.Thread(target=browse, args=(args,))
            browseThread.start()
        else:
            args['ivr'] = getIvr()
            startIvr(args['ivr'])

    if data['type'] == 'CALL_DTMF_START':
        if (args['ivr'] and len(args['browsing'].room) != maxDigits and
            args['browse_lock'].acquire(blocking=False)):
            print(data, flush=True)
            args['browsing'].room = args['browsing'].room + data['param']
            args['browse_lock'].release()
            wait = 10 #ms
            if len(args['browsing'].room) == maxDigits:
                browseThread = threading.Thread(target=browse, args=(args,))
                browseThread.start()
                wait = 1000 #ms

            args['ivr'].show(args['browsing'].width, args['browsing'].height,
                             args['browsing'].room +
                             ' *'*(maxDigits-len(args['browsing'].room)),
                             wait)

            if len(args['browsing'].room) == 0:
                args['ivr'].show(args['browsing'].width, args['browsing'].height,
                                 ' *'*maxDigits)

    if data['type'] == 'CALL_CLOSED':
        endBrowse(args)
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

argDict = {'browsing':browsingObj(dispWidth, dispHeight, inputs['room']),
           'browse_error':False,
           'browse_lock': threading.Lock(),
           'ivr':None}

ns.getEvents(event_handler, argDict)

# Terminate
endBrowse(argDict)

sys.exit(0)

