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

bbbFQDN = os.environ.get('WEBRTC_DOMAIN')
if not bbbFQDN:
    bbbFQDN = "demo.bigbluebutton.org/rooms"

captureVideoQuality="high" # low, medium, high, hd

class BigBlueButton (Browsing):

    def setUrl(self):
        self.url = 'https://{}/{}/join'.format(bbbFQDN, self.room)
        print("Web browsing URL: "+self.url, flush=True)

    def browse(self, driver):
        # Enter name
        try:
            element = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.CSS_SELECTOR, '#joinFormName')))
            element.send_keys(self.name)
            element.submit()
        except Exception as e:
            print("Name submit failed", flush=True)

        # Activate microphone
        try:
            element = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.CSS_SELECTOR,"[aria-label=Microphone]")))
            element.click()

            test=WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "option[value='default']")))

            element = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.CSS_SELECTOR,"[data-test=joinEchoTestButton]")))
            element.click()
        except Exception as e:
            print("Microphone activation failed", flush=True)

        # Activate camera
        try:
            element = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.CSS_SELECTOR,".icon-bbb-video_off")))
            element.click()
            element = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.CSS_SELECTOR,"#setQuality")))
            select = Select(element)
            select.select_by_value(captureVideoQuality)
            time.sleep(1)
            self.driver.execute_script("document.querySelectorAll('[data-test=\"startSharingWebcam\"]')[0].click();")
        except Exception as e:
            print("Camera activation failed", flush=True)

