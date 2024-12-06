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

bbbFQDN = os.environ.get('WEBRTC_DOMAIN')
if not bbbFQDN:
    bbbFQDN = "demo.bigbluebutton.org/rooms"

captureVideoQuality="high" # low, medium, high, hd

# Custom click function that relies on exceptions
def tryClick(driver, selector, attempts=5, timeout=20):
    count = 0
    while count < attempts:
        try:
            element = WebDriverWait(driver, timeout).until(EC.element_to_be_clickable((By.CSS_SELECTOR, selector)))
            element.click()
            return element

        except WebDriverException as e:
                print("Retry click", flush=True)
                count = count + 1

    raise TimeoutException('Custom click timed out')

class BigBlueButton (Browsing):

    def setUrl(self):
        self.url = 'https://{}/{}'.format(bbbFQDN, self.room)
        print("Web browsing URL: "+self.url, flush=True)

    def chatHandler(self):
        try:
            message = self.chatMsg.get(True, 0.02)
            if hasattr(self, 'chatInput') and hasattr(self, 'sendChatMsg'):
                self.chatInput.send_keys(message)
                self.sendChatMsg.click()
        except Exception as e:
            pass
        try:
            input = self.userInputs.get(True, 0.02)
            if input == 'c':
                self.toggleChat.click()
                self.chatInput = WebDriverWait(self.driver, 1).until(EC.element_to_be_clickable((By.ID,"message-input")))
                self.sendChatMsg = WebDriverWait(self.driver, 1).until(EC.element_to_be_clickable((By.CSS_SELECTOR,'[data-test="sendMessageButton"]')))

        except Exception as e:
            pass

    def browse(self, driver):

        # Accept Cookies
        try:
            tryClick(driver, "#okcookie", 4, 1)
        except Exception as e:
            print("Cookie acceptation failed", flush=True)

        # Enter name
        try:
            element = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.CSS_SELECTOR, '#joinFormName')))
            #element = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.CSS_SELECTOR, '#fullname')))
            #element = WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.CSS_SELECTOR, "#id_name")))
            element.send_keys(self.name)
            element.submit()
        except Exception as e:
            print("Name submit failed", flush=True)

        # Activate microphone
        try:
            tryClick(driver, "[aria-label='Join audio']", 5, 10)
        except Exception as e:
            print("Microphone activation failed", flush=True)

        # Activate camera
        try:
            tryClick(driver, ".icon-bbb-video_off", 5, 10)
            element = WebDriverWait(driver, 60).until(EC.element_to_be_clickable((By.CSS_SELECTOR,"#setQuality")))
            select = Select(element)
            select.select_by_value(captureVideoQuality)
            element = tryClick(driver, '[data-test=\"startSharingWebcam\"]', 5, 20)
            while element:
                element.click()
                try:
                    element = WebDriverWait(driver, 60).until(EC.element_to_be_clickable((By.CSS_SELECTOR,"[data-test=\"startSharingWebcam\"]")))
                except:
                    pass

        except Exception as e:
            print("Camera activation failed", flush=True)

        # Detect Chat
        try:
            self.toggleChat = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.CSS_SELECTOR,'#chat-toggle-button')))
            self.chatInput = WebDriverWait(driver, 1).until(EC.element_to_be_clickable((By.ID,"message-input")))
            self.sendChatMsg = WebDriverWait(driver, 1).until(EC.element_to_be_clickable((By.CSS_SELECTOR,'[data-test="sendMessageButton"]')))
        except Exception as e:
            print("Chat detection failed", flush=True)

        while self.url:
            self.chatHandler()

