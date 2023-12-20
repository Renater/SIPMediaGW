#!/usr/bin/env python3
import os
import subprocess

coturnRunCmd='turnserver --log-file=stdout --lt-cred-mech \
                         --min-port=40000 --max-port=49999'

if os.getenv("STUN_SRV"):
    coturnRunCmd+= ' --external-ip={}/{}'.format(os.getenv("STUN_SRV"),os.getenv("LOCAL_IP"))

coturnRunCmd+=' --user={}:{}'.format(os.getenv("STUN_USER"), os.getenv("STUN_PASS"))

print("Coturn run command: {}".format(coturnRunCmd), flush=True)

cmd = subprocess.Popen(coturnRunCmd,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)

cmd.wait()
