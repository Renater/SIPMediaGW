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

webRTCmeetingFQDN = os.environ.get('DOMAIN')
if not webRTCmeetingFQDN:
    webRTCmeetingFQDN = "usually.in"

captureVideoQuality="high" # low, medium, high, hd

# Custom click function that relies on exceptions
def tryClick(driver, selector, attempts=5, timeout=20):
    count = 0
    while count < attempts:
        try:
            time.sleep(1)
            element = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
            element.click()
            return element

        except WebDriverException as e:
            if ('is not clickable at point' in str(e)):
                print("Retry click", flush=True)
                count = count + 1
            else:
                raise e

    raise TimeoutException('Custom click timed out')

class EduMeet (Browsing):

    def setUrl(self):
        self.url = 'https://{}/{}'.format(webRTCmeetingFQDN, self.room)
        print("Web browsing URL: "+self.url, flush=True)

    def browse(self, driver):
        # Enter name
        try:
            element = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[type='text']")))
            element.send_keys(self.name)
            element.submit()
        except Exception as e:
            print("Name submit failed", flush=True)

        # Join
        try:
            tryClick(driver, "div:nth-of-type(2) > div:nth-of-type(3) > div > div:nth-of-type(2) > button", 5, 40)
        except Exception as e:
            print("Join Failed", flush=True)

        while self.url:
            time.sleep(1)

