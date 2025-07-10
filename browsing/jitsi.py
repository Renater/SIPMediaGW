#!/usr/bin/env python

import sys
import time
import os
import json
import time
from browsing import Browsing
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support import expected_conditions as EC
import traceback


class Jitsi (Browsing):

    def chatHandler(self):
        try:
            message = self.chatMsg.get(True, 0.01).strip()
            chatCmd = "window.jitsiApiClient.executeCommand('sendChatMessage', '{}')".format(message)
            self.driver.execute_script(chatCmd)
        except Exception as e:
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

        initScript = "jitsi=new Jitsi('{}', '{}', '{}', '{}', '{}'); \
                      window.meeting = jitsi".format( self.config['webrtc_domain'],
                                                      room['roomName'],
                                                      room['displayName'],
                                                      self.config['lang'],
                                                      room['roomToken'])

        self.loadJS(os.path.join(os.path.dirname(os.path.normpath(__file__)),'./assets/jitsi.js'))
        self.driver.execute_script(initScript)
        self.driver.execute_script("jitsi.join();")

        # Jitsi
        try:
            driver.switch_to.default_content()
            jitsiUrl = self.driver.execute_script("return window.jitsiApiClient._url;")
            print("Jitsi URL: "+jitsiUrl, flush=True)
        except Exception as e:
            print("Iframe to defaut content switching error", flush=True)
            try:
                jitsiUrl = self.driver.execute_script("return window.location.href;")
            except:
                return
            print("Jitsi URL: "+jitsiUrl, flush=True)

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

    def unset(self):
        try:
            self.driver.execute_script(
                "if ( jitsi ) { jitsi.leave(); }"
            )
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
            print("Meeting logout error: {}".format(e), flush=True)

