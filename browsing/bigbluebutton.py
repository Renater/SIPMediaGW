#!/usr/bin/env python

import sys
import time
import traceback
from browsing import Browsing
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

class BigBlueButton (Browsing):

    def setUrl(self):
        self.url = 'https://demo.bigbluebutton.org/'+self.room
        print("Web browsing URL: "+self.url, flush=True)

    def browse(self, driver):
        # Accept Cookies
        try:
            element = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.CSS_SELECTOR,"#cookies-agree-button")))
            element.click()
        except Exception as e:
            print("Cookies banner not found", flush=True)

        # Enter name
        roomParts = self.room.split('/')
        selector = '#_'+roomParts[0]+'_'+roomParts[1]+'_join_name'
        try:
              element = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.CSS_SELECTOR,selector)))
              all_options = element.find_elements_by_tag_name("option")
              element.send_keys(self.name)
              element.submit()
        except Exception as e:
              print("Name submit failed", flush=True)

        # Activate microphone
        try:
            element = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.CSS_SELECTOR,"button.jumbo--Z12Rgj4:nth-child(1)")))
            element.click()
            element = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.CSS_SELECTOR,"button.jumbo--Z12Rgj4:nth-child(1)")))
            element.click()
        except Exception as e:
            print("Microphone activation failed", flush=True)

        # Activate camera
        time.sleep(10)
        try:
            element = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.CSS_SELECTOR,".icon-bbb-video_off")))
            element.click()
            time.sleep(2)
            element = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.CSS_SELECTOR,".actions--15NFtQ")))
            element.click()
        except Exception as e:
            print("Camera activation failed", flush=True)

args = sys.argv
name = args[2]
room = args[1]

dispRes = args[3]
dispWidth = dispRes.split('x')[0]
dispHeight = dispRes.split('x')[1]

bbb = BigBlueButton(room, name, dispWidth, dispHeight)
bbb.run()

