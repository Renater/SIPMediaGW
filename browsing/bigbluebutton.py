#!/usr/bin/env python
import time
import os
import sys
import json
import traceback
from browsing import Browsing
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException
from selenium.common.exceptions import TimeoutException

class BigBlueButton (Browsing):

    def chatHandler(self):
        try:
            message = self.chatMsg.get(True, 0.02)
            self.driver.execute_script('bbb.typeText("{}")'.format(message))
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

        self.driver.execute_script('window.location.href = "https://{}/{}";'.format(
                                    self.config['webrtc_domain'],
                                    room['roomName']))

        initScript = "bbb=new Bigbluebutton('{}', '{}', '{}', '{}', '{}'); \
                      window.meeting = bbb".format( self.config['webrtc_domain'],
                                                    room['roomName'],
                                                    room['displayName'],
                                                    self.config['lang'],
                                                    room['roomToken'])

        self.loadJS(os.path.join(os.path.dirname(os.path.normpath(__file__)),'./assets/bigbluebutton.js'))
        self.driver.execute_script(initScript)
        self.driver.execute_script("bbb.join();")

        # BigBlueButton
        try:
            WebDriverWait(self.driver, 10).until(EC.url_contains("sessionToken"))
        except:
            print("Cannot enter meeting", flush=True)
            return

        self.loadJS(os.path.join(os.path.dirname(os.path.normpath(__file__)),'./assets/bigbluebutton.js'))
        self.driver.execute_script(initScript)
        self.driver.execute_script("bbb.browse();")

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
                "if ( bbb ) { bbb.leave(); }"
            )
            # Waiting for the leaveMeetingDropdown button to disappear (max 10s)
            WebDriverWait(self.driver, 10).until(
                EC.invisibility_of_element_located((By.CSS_SELECTOR, '[data-test="leaveMeetingDropdown"]'))
            )
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
            print("Meeting logout error: {}".format(e), flush=True)