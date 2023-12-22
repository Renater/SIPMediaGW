#!/usr/bin/env python

import sys
import os
import time
import traceback
import queue
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
        self.UIKeyMap = {}
        self.driver = []
        self.service = []
        self.chromeOptions = webdriver.ChromeOptions()
        self.chromeOptions.add_argument('--no-sandbox')
        self.chromeOptions.add_argument('--disable-web-security')
        self.chromeOptions.add_argument('--disable-site-isolation-trials')
        #self.chromeOptions.add_argument('--use-fake-ui-for-media-stream')
        self.chromeOptions.add_argument('--auto-select-desktop-capture-source=Screen 2')
        self.chromeOptions.add_argument('--enable-usermedia-screen-capturing')
        self.chromeOptions.add_argument('--disable-gpu')
        self.chromeOptions.add_argument('--start-fullscreen')
        self.chromeOptions.add_argument('--kiosk')
        self.chromeOptions.add_argument('--window-size='+str(width)+','+str(height))
        self.chromeOptions.add_argument('--window-position=0,0')
        self.chromeOptions.add_argument('--hide-scrollbars')
        self.chromeOptions.add_argument('--disable-notifications')
        self.chromeOptions.add_argument('--autoplay-policy=no-user-gesture-required')
        self.chromeOptions.add_experimental_option("excludeSwitches", ['enable-automation', 'test-type'])
        self.chromeOptions.add_experimental_option('prefs',{'profile.default_content_setting_values.media_stream_mic':1,
                                                            'profile.default_content_setting_values.media_stream_camera':1})

        policyFile = "/etc/opt/chrome/policies/managed/managed_policies.json"
        os.makedirs(os.path.dirname(policyFile), exist_ok=True)
        with open(policyFile, "w") as f:
            f.write('{ "CommandLineFlagSecurityWarningsEnabled": false }')
        f.close()

    def setUrl(self):
        pass

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
        except Exception:
            return

        try:
            self.driver.execute_script(self.UIKeyMap[inKey])
        except Exception as e:
            print("User input error", flush=True)

    def unset(self):
        pass

    def stop(self):
        try:
            self.unset()
            self.room=''
            self.name=''
            self.url=''
            if self.driver:
                self.driver.close()
                self.driver.quit()
                self.driver = []
                print("Browsing stopped", flush=True)
        except Exception as e:
            traceback.print_exc(file=sys.stdout)


