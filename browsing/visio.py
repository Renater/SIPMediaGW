#!/usr/bin/env python

import sys
import time
import os
import requests
import json
import subprocess
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
        self.url = 'https://{}/{}?skipPreJoin=True&username={}'.format(livekitFQDN, 
                                                                        self.room,
                                                                        self.name)
        print("Web browsing URL: "+self.url, flush=True)

    def interactVisio(self):
        try:
            inKey = self.userInputs.get(True, 0.02)
        except Exception:
            return

        try:
            if inKey == "1":
                #subprocess.run(["xdotool", "key", "ctrl+d"])
                element = WebDriverWait(self.driver, 60).until(EC.element_to_be_clickable((By.XPATH, "//button[contains(@aria-label, '(Ctrl+d)')]")))
                element.click()
            if inKey == "2":
                #subprocess.run(["xdotool", "key", "ctrl+e"])    
                element = WebDriverWait(self.driver, 60).until(EC.element_to_be_clickable((By.XPATH, "//button[contains(@aria-label, '(Ctrl+e)')]")))
                element.click()
            if inKey == "3": 
                element = WebDriverWait(self.driver, 60).until(EC.element_to_be_clickable((By.XPATH, 
                "//button[contains(@aria-label, 'Open the chat') or contains(@aria-label, 'Close the chat')]")))
                element.click()
            if inKey == "4":  
                element = WebDriverWait(self.driver, 60).until(EC.element_to_be_clickable((By.XPATH, 
                "//button[contains(@aria-label, 'Raise hand') or contains(@aria-label, 'Lower hand')]")))
                element.click()
            if inKey == "5":  
                element = WebDriverWait(self.driver, 60).until(EC.element_to_be_clickable((By.XPATH, 
                "//button[contains(@aria-label, 'See everyone') or contains(@aria-label, 'Hide everyone')]")))
                element.click()
            if inKey == "#":  
                subprocess.Popen(
                    ["ffplay", "/var/browsing/assets/menu.mp4", 
                     "-left", "20", "-top", "420", "-t", "7", "-autoexit", "-noborder"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL)
                time.sleep(0.5)
                subprocess.run(
                    ["wmctrl", "-r", "menu.mp4", "-b", "add,above"])

        except Exception as e:
            print("User input error: {}".format(e), flush=True)
            return


    def browse(self, driver):

        subprocess.Popen(
            ["ffplay", "/var/browsing/assets/icon.png", "-left", "20", "-top", "620", "-noborder"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL)
        time.sleep(0.5)
        subprocess.run(
            ["wmctrl", "-r", "icon.png", "-b", "add,above"])

        actions = ActionChains(self.driver)
        while self.url:
            #time.sleep(1)
            try:
                self.interactVisio()
            except:
                pass


