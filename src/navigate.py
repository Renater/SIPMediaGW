#!/usr/bin/env python

import sys
import atexit
import time
import os
import subprocess
import signal
import threading
sys.path.append(os.path.dirname('./ivr.py'))
from ivr import IVR

from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def exit_handler():
    subprocess.run(['echo "/quit" | netcat -q 1 127.0.0.1 5555'],
             shell=True)

def browse(ivr):
    ivr.chromeOptions.arguments.remove('--start-fullscreen')
    ivr.chromeOptions.arguments.remove('--kiosk')
    ivr.run()
    subprocess.run(['echo "/hangup" | netcat -q 1 127.0.0.1 5555'],
         shell=True)

atexit.register(exit_handler)
signal.signal(signal.SIGTERM, exit_handler)
signal.signal(signal.SIGINT, exit_handler)

# Get a browsing object from the browsing file name
os.environ['IVR_TIMEOUT'] =  '600'
os.environ['MAIN_APP'] =  'recording'
os.environ['ENDING_TIMEOUT'] = "900"
ivr = IVR('1280', '720', 'bob/xxxx_dsdsd-sd-sds-d', 'Nico', '')

#browsingInst.run()
browseThread = threading.Thread(target=browse, args=(ivr,))
browseThread.start()

while True:
    time.sleep(1)

sys.exit(0)

