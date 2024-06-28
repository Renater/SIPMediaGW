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

#teamsFQDN = os.environ.get('WEBRTC_DOMAIN')
#if not teamsFQDN:
#teamsFQDN = "teams.live.com/meet"
teamsFQDN = "teams.microsoft.com/v2/?meetingjoin=true#/meet"
#352026135202?p=ve7NYu

def getIframe(driver, timeout):
    script = """try{{
                    return document.querySelector("iframe");
                }}
                catch{{return false}}"""

    res = "Iframe not found"
    iframe = None
    start = time.time()
    while time.time() - start < timeout:
        iframe = driver.execute_script(script)
        if driver and iframe:
            res = "Iframe found"
            break
        time.sleep(1)
    print("Get Iframe : {}".format(res), flush=True)
    return iframe

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

class Teams (Browsing):

    def setUrl(self):
        self.url = 'https://{}/{}'.format(teamsFQDN, self.room)
        print("Web browsing URL: "+self.url, flush=True)

    def browse(self, driver):

        # Disable background suppression (audio) and enter name
        try:
            #iframe = getIframe(self.driver, 60)
            #driver.switch_to.frame(iframe)
            element = WebDriverWait(driver, 60).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "[data-tid='toggle-devicesettings-computeraudio']")))
            element.click()
            element = WebDriverWait(driver, 60).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "[data-tid='background-suppression-switch-div']")))
            element.click()
            element = WebDriverWait(driver, 60).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "[data-tid='prejoin-display-name-input']")))
            element.send_keys(self.name)
            element = WebDriverWait(driver, 60).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "[data-tid='prejoin-join-button']")))
            element.click()
        except Exception as e:
            print("Name submit failed", flush=True)

        while self.url:
            time.sleep(1)

