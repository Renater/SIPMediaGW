#!/usr/bin/env python

import sys
import time
import traceback
from browsing import Browsing
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

class RendezVousJitsi (Browsing):

    def setUrl(self):
        self.url = 'https://rendez-vous.renater.fr/'+self.room+'#userInfo.displayName="'+self.name+'"'
        print("Web browsing URL: "+self.url, flush=True)

    def browse(self, driver):
        # Validate MOTD
        try:
            element = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.CSS_SELECTOR,"#motd_do_not_show_again")))
            element.click()
        except Exception as e:
            print("MOTD not found", flush=True)

        # Accept Cookies
        try:
            element = WebDriverWait(driver, 20).until(EC.element_to_be_clickable((By.CSS_SELECTOR,"#cookie_footer > section > section > section > a")))
            element.click()
        except Exception as e:
            print("Cookies banner not found", flush=True)

args = sys.argv
name = args[2]
room = args[1]

dispRes = args[3]
dispWidth = dispRes.split('x')[0]
dispHeight = dispRes.split('x')[1]

rdvJitsi = RendezVousJitsi(room, name, dispWidth, dispHeight)
rdvJitsi.run()
