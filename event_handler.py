#!/usr/bin/env python

import socket
import sys
import time
import os.path
import signal
import argparse
import json
import requests
import re
from baresip.netstring import Netstring


# Default Baresip host
baresipHost = "localhost"

args = sys.argv

parser = argparse.ArgumentParser(description='Event handler script')
parser.add_argument('-l','--log', help='Log file', required=False)
parser.add_argument('-a','--addr', help='Baresip IP', required=False)
args = vars(parser.parse_args())

if args['log']:
    appLogs = open(args['log'], "a")
else:
    appLogs = sys.stdout

if args['addr']:
    baresipHost = args['addr']


def uaStat (ns: Netstring):
    m = {"command":"uastat"}
    res = ns.sendCommand(m)
    ansiEscape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    uaStat = (ansiEscape.sub('', res[0]['data'])).split('\n\n')

    return uaStat


def event_handler(data):
    if data['type'] == 'CALL_ESTABLISHED':
        return 1
    return 0


def abort(signum, frame):
    sys.exit(1)

signal.signal(signal.SIGINT, abort)
signal.signal(signal.SIGTERM, abort)

ns = Netstring(baresipHost, 4444)
ns.getEvents(event_handler)

sys.exit(0)

