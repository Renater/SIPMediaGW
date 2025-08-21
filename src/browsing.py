#!/usr/bin/env python

import sys
import os
import time
import traceback
import queue
import shutil
import subprocess
import json
import base64
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.remote.remote_connection import LOGGER, logging
from selenium.webdriver.chrome.service import Service

class Browsing:
    def __init__(self, width, height, room=None, name=None):
        self.url = ''
        self.room = room if room else ''
        self.name = name if name else ''
        self.width = width
        self.height = height
        self.screenShared = False
        self.userInputs = queue.Queue()
        self.chatMsg = queue.Queue()
        self.IVRTimeout = int(os.environ.get('IVR_TIMEOUT'))
        self.driver = []
        self.service = []
        self.chromeOptions = webdriver.ChromeOptions()
        self.chromeOptions.add_argument('--no-sandbox')
        self.chromeOptions.add_argument('--disable-web-security')
        self.chromeOptions.add_argument('--disable-site-isolation-trials')
        #self.chromeOptions.add_argument('--use-fake-ui-for-media-stream')
        self.chromeOptions.add_argument('--auto-select-desktop-capture-source=Screen 2')
        self.chromeOptions.add_argument('--screen-capture-audio-default-unchecked')
        self.chromeOptions.add_argument('--enable-usermedia-screen-capturing')
        self.chromeOptions.add_argument('--disable-gpu')
        self.chromeOptions.add_argument('--start-fullscreen')
        self.chromeOptions.add_argument('--kiosk')
        self.chromeOptions.add_argument('--window-size='+str(width)+','+str(height))
        self.chromeOptions.add_argument('--window-position=0,0')
        self.chromeOptions.add_argument('--hide-scrollbars')
        self.chromeOptions.add_argument('--disable-notifications')
        self.chromeOptions.add_argument('--autoplay-policy=no-user-gesture-required')
        if os.environ.get('WITH-ALSA') == "true":
            self.chromeOptions.add_argument('--alsa-input-device=hw:1,1')
            self.chromeOptions.add_argument('--alsa-output-device=hw:0,0')
        self.chromeOptions.add_experimental_option("excludeSwitches", ['enable-automation', 'test-type'])
        self.chromeOptions.add_experimental_option('prefs',{'profile.default_content_setting_values.media_stream_mic':1,
                                                            'profile.default_content_setting_values.media_stream_camera':1})

        policyFile = "/etc/opt/chrome/policies/managed/managed_policies.json"
        os.makedirs(os.path.dirname(policyFile), exist_ok=True)
        with open(policyFile, "w") as f:
            f.write('{ "CommandLineFlagSecurityWarningsEnabled": false }')
        f.close()

    def setUrl(self):
        configFile = os.path.join(os.path.dirname(os.path.normpath(__file__)), '../browsing/assets/config.json')
        with open(configFile) as f:
            self.config = json.load(f)
        IVRPath = "file://"
        IVRPath += os.path.join(os.path.dirname(os.path.normpath(__file__)), '../browsing/assets/IVR/index.html')
        self.url = '{}?displayName={}'.format(IVRPath, self.name)
        if self.room:
            self.url = '{}&roomId={}'.format(self.url, self.room)
        print("Web browsing URL: "+self.url, flush=True)

    def loadJS(self, jsScript):
        with open(jsScript, "r", encoding="utf-8") as f:
            js_code = f.read()
        self.driver.execute_script(js_code)

    def loadImages(self, path, lang):
        with open(path + "icon.png", "rb") as f:
            self.iconB64 = "data:image/png;base64,{}".format(base64.b64encode(f.read()).decode("utf-8"))
        with open( path + "dtmf_{}.png".format(lang), "rb") as f:
            self.dtmfB64 = "data:image/png;base64,{}".format(base64.b64encode(f.read()).decode("utf-8"))

    def browse(self, driver):
        pass

    def run(self):
        try:
            self.setUrl()
            if not self.url:
                return 1
            self.service = Service(executable_path='/usr/bin/chromedriver')
            self.driver = webdriver.Chrome(service=self.service,
                                           options=self.chromeOptions)
            self.driver.get(self.url)
            self.browse(self.driver)

            return 0

        except Exception as e:
            traceback.print_exc(file=sys.stdout)
            return 1

    def interact(self):
        try:
            inKey = self.userInputs.get(True, 0.02)
        except Exception as e:
            return
        self.driver.execute_script(f"document.dispatchEvent(new KeyboardEvent('keydown',{{'key':'{inKey}'}}));")

    def IVR(self):
        startTime = time.time()
        while True:
            if self.IVRTimeout and time.time() > ( startTime + self.IVRTimeout ):
                print("IVR Timeout", flush=True)
                return
            try:
                room = self.driver.execute_script("return window.room")
                if room:
                    return room
                self.interact()
            except:
                return {}

    def unset(self):
        pass

    def stop(self):
        try:
            self.room=''
            self.name=''
            self.url=''
            if self.driver:
                if self.driver.execute_script("return window.meeting"):
                    self.unset()
                self.driver.close()
                self.driver.quit()
                self.driver = []
                print("Browsing stopped", flush=True)
        except Exception as e:
            traceback.print_exc(file=sys.stdout)


