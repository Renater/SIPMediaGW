#!/usr/bin/env python
import sys
import atexit
import time
import os
import re
import json
import subprocess
import signal
import threading
import urllib.parse

sys.path.append(f"{os.path.dirname(os.path.abspath(__file__))}/../src")
from ivr import IVR
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def parseEnvFile(envPath):
    envVars = {}
    multilineKey = None
    multilineVal = []

    with open(envPath) as file:
        for line in file:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            # Multiline value (for JSON)
            if multilineKey:
                if line.endswith("'"):
                    multilineVal.append(line[:-1])
                    val = "\n".join(multilineVal)
                    envVars[multilineKey] = val
                    multilineKey = None
                    multilineVal = []
                else:
                    multilineVal.append(line)
                continue

            # Remove inline comments
            line = re.sub(r'\s+#.*$', '', line)
            if '=' not in line:
                continue

            key, val = line.split('=', 1)
            key = key.strip()
            val = val.strip()

            # Handle multiline JSON (starts and ends with single quote)
            if val.startswith("'") and not val.endswith("'"):
                multilineKey = key
                multilineVal = [val[1:]]
                continue

            val = val.strip('"').strip("'")

            # If ${VAR:-default}
            match = re.match(r'\$\{([A-Za-z0-9_]+):-([^\}]*)\}', val)
            if match:
                default = match.group(2)
                # If default contains a $ (anywhere), set to ''
                if '$' in default:
                    val = ''
                else:
                    val = default
            # If ${VAR}, set to ''
            elif re.match(r'\$\{[A-Za-z0-9_]+\}', val):
                val = ''

            envVars[key] = val

    return envVars

def exitHandler():
    subprocess.run(
        ['echo "/quit" | netcat -q 1 127.0.0.1 5555'],
        shell=True
    )

def browse(ivr):
    ivr.chromeOptions.arguments.remove('--start-fullscreen')
    ivr.chromeOptions.arguments.remove('--kiosk')
    ivr.run()

atexit.register(exitHandler)
signal.signal(signal.SIGTERM, exitHandler)
signal.signal(signal.SIGINT, exitHandler)

# Set environment variables
envPath = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../.env')
envVars = parseEnvFile(envPath)
for key, value in envVars.items():
    os.environ[key] = value

def envsubst(string):
    return re.sub(
        r'\$\{([A-Za-z0-9_]+)\}',
        lambda match: os.environ.get(match.group(1), ""),
        string
    )

templatePath = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../browsing/assets/config.template.json')
configPath = os.path.join(os.path.dirname(os.path.abspath(__file__)), '../browsing/assets/config.json')

with open(templatePath) as file:
    content = file.read()

with open(configPath, "w") as file:
    config = json.loads(envsubst(content))
    file.write(json.dumps(config, indent=4))

# Launch IVR
# os.environ['AUDIO_ONLY'] = "true"
# mixedRoomDomainId = '1.2483803751'
ivr = IVR(width='1280', height='720', roomName='myroom', name='myname', mixedId='')
browseThread = threading.Thread(target=browse, args=(ivr,))
browseThread.start()

while True:
    time.sleep(1)

sys.exit(0)
