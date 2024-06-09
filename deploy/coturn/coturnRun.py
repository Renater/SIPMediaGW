#!/usr/bin/env python3
import os
import subprocess

coturnRunCmd='turnserver --log-file=stdout --lt-cred-mech \
                         --min-port=40000 --max-port=49999'

if os.getenv("PUBLIC_IP"):
    coturnRunCmd+= ' --external-ip={}'.format(os.getenv("PUBLIC_IP"))
    if  os.getenv("LOCAL_IP"):
        coturnRunCmd+= '/{}'.format(os.getenv("LOCAL_IP"))

coturnRunCmd+=' --user={}:{}'.format(os.getenv("TURN_USER"), os.getenv("TURN_PASS"))

print("Coturn run command: {}".format(coturnRunCmd), flush=True)

cmd = subprocess.Popen(coturnRunCmd,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)

cmd.wait()
