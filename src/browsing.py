#!/usr/bin/env python

import sys
import os
import time
import traceback
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.common.desired_capabilities import DesiredCapabilities
from selenium.webdriver.remote.remote_connection import LOGGER, logging

class Browsing:
    def __init__(self, width, height, room=None, name=None):
        self.url = ''
        self.room = room if room else ''
        self.name = name if name else ''
        self.width = width
        self.height= height
        self.driver = []
        self.desiredCaps = DesiredCapabilities.CHROME
        self.serviceArgs = []
        self.chromeOptions = Options()
        self.chromeOptions.add_argument('--no-sandbox')
        self.chromeOptions.add_argument('--use-fake-ui-for-media-stream')
        self.chromeOptions.add_argument('--disable-dev-shm-usage')
        self.chromeOptions.add_argument('--disable-gpu')
        self.chromeOptions.add_argument('--start-fullscreen')
        self.chromeOptions.add_argument('--window-size='+str(width)+','+str(height))
        self.chromeOptions.add_argument('--window-position=0,0')
        self.chromeOptions.add_argument('--hide-scrollbars')
        self.chromeOptions.add_argument('--disable-notifications')
        self.chromeOptions.add_experimental_option("excludeSwitches", ['enable-automation'])
        gwId = int(os.environ.get('GW_ID'))
        self.chromeOptions.add_argument("--alsa-input-device=plughw:{},0".format(2*gwId))
        self.chromeOptions.add_argument("--alsa-output-device=plughw:{},1".format(2*gwId+1))

    def setUrl(self):
        pass

    def browse(self, driver):
        pass

    def run(self):
        try:
            self.setUrl()
            if not self.url:
                return 1
            self.driver = webdriver.Chrome('/usr/bin/chromedriver',
                                           desired_capabilities=self.desiredCaps,
                                           options=self.chromeOptions,
                                           service_args=self.serviceArgs)
            self.driver.get(self.url)
            self.browse(self.driver)

            return 0

        except Exception as e:
            traceback.print_exc(file=sys.stdout)
            return 1

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


