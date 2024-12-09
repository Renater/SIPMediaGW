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

livekitFQDN = os.environ.get('WEBRTC_DOMAIN')
if not livekitFQDN:
    livekitFQDN = "meet.livekit.io/rooms"

class Livekit (Browsing):

    def setUrl(self):
        self.url = 'https://{}/{}'.format(livekitFQDN, self.room)
        print("Web browsing URL: "+self.url, flush=True)

    def browse(self, driver):

        # Enter name
        try:
            element = WebDriverWait(driver, 60).until(EC.element_to_be_clickable((By.ID, "username")))
            element.send_keys(self.name)
            element.send_keys(Keys.RETURN)
        except Exception as e:
            print("Name submit failed", flush=True)

        actions = ActionChains(self.driver)
        while self.url:
            time.sleep(1)
            try:
                self.driver.switch_to.alert.accept()
            except:
                pass

