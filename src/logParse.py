#!/usr/bin/env python3

import fileinput

import re
import os
import sys
import time
from datetime import datetime
import requests
import json
import argparse

postURL = os.environ.get('LOG_PUSH_URL')

statPats = r'^(video|audio)(\s+Transmit:)(\s+Receive:)$'
statPat  = re.compile(statPats)
statFields = {'packets', 'errors', 'pkt.report', 'avg. bitrate', 'lost', 'jitter'}

def pushHistory(history):
    try:
        data = {}
        data['room'] = 'IVR'
        with open(history, 'r') as f:
            for line in f:
                key, log = line.split(':',1)
                if key not in data:
                    data[key] = log
                else:
                    data[key]+= '{}'.format(log)

        url = "{}?room={}".format(postURL, data['room'])
        headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}
        r = requests.post( url, data=json.dumps(data), headers=headers)
        if r.status_code != 200:
            print("Failed to post call history, status_code: {}".format(r.status_code) )
    except Exception as exc:
        print("Failed to post call history: ", exc)


def getLogsData (log, key, history):
    try:
        f = open(history, 'a')
        f.write('{}:{}'.format(key, log))
        f.close()
        if key == 'end' and postURL:
            pushHistory(history)
    except Exception as exc:
        print("Failed to get logs data: ", exc)


def main():
    inputs = sys.argv
    parser = argparse.ArgumentParser(description='Log parser')
    parser.add_argument('-p','--pref', help='log prefix', required=True)
    parser.add_argument('-i','--history', help='history file', required=False)
    inputs = vars(parser.parse_args())
    pref = inputs['pref']
    with open('/dev/stdin') as f:
        for l in f:
            line = l.rstrip()
            ansiEscape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
            line = ansiEscape.sub('', line)
            if not line:
                continue
            print('{}: {}'.format(pref, line), flush=True)
            if not inputs['history']:
                continue
            historyFile = inputs['history']

            try:
                if 'Web browsing URL:' in line:
                    getLogsData ('{}\n'.format(datetime.now().strftime("%b %d %H:%M:%S")),
                                 'start_call', historyFile)
                    getLogsData ('{}\n'.format(line.split('URL: ',1)[1]),
                                 'url', historyFile)

                if 'Jitsi URL:' in line:
                    getLogsData ('{}\n'.format(line.split('#',1)[0].
                                               rsplit("/",1)[1]),
                                 'room', historyFile)

                if pref == "Baresip":
                    if (statPat.fullmatch(line) or 
                        line.split(':')[0] in statFields):
                        getLogsData ('{}\n'.format(line),
                                     'stats', historyFile)

                if 'ua: stop all' in line:
                    getLogsData ('{}\n'.format(datetime.now().strftime("%b %d %H:%M:%S")),
                                 'end', historyFile)

            except Exception as exc:
                print("Failed to parse log line: ", exc)

if __name__ == "__main__":
    main()

