#!/usr/bin/env python

import sys
import time
import os
import requests
import json
from browsing import Browsing
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException
from selenium.common.exceptions import TimeoutException

teamsFQDN="teams.live.com/meet"

class Teams (Browsing):

    def chatHandler(self):
        pass

    def browse(self, driver):

        # IVR
        try:
            WebDriverWait(self.driver, 5).until(EC.presence_of_element_located((By.ID,"digits")))
        except:
            print("Cannot find IVR", flush=True)
            return
        room = self.IVR()
        if not room:
            return

        self.driver.get("https://{}/{}".format(
            self.config['webrtc_domain'],
            room['roomName'].replace('-', '?p=')
        ))

        initScript = "teams=new Teams('{}', '{}', '{}', '{}', '{}'); \
                      window.meeting = teams".format( self.config['webrtc_domain'],
                                                      room['roomName'],
                                                      room['displayName'],
                                                      self.config['lang'],
                                                      room['roomToken'])

        WebDriverWait(self.driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "video"))
        )

        self.loadJS(os.path.join(os.path.dirname(os.path.normpath(__file__)),'./assets/teams.js'))
        self.driver.execute_script(initScript)
        self.driver.execute_script("teams.join();")

        # Teams
        self.loadImages(os.path.join(os.path.dirname(os.path.normpath(__file__)),'./assets/'),
                        self.config['lang'])
        menuScript = "menu=new Menu(); \
                      menu.img['icon'] = '{}'; \
                      menu.img['dtmf'] = '{}'; \
                      menu.show();".format(self.iconB64, self.dtmfB64)
        self.loadJS(os.path.join(os.path.dirname(os.path.normpath(__file__)),'./assets/IVR/menu.js'))
        self.driver.execute_script(menuScript)

        while self.url:
            self.interact()
            self.chatHandler()

