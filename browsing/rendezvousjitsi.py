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
        self.url =  'https://rendez-vous.renater.fr/' + self.room
        self.url += '#userInfo.displayName="' + self.name + '"'
        self.url += '&config.enableNoisyMicDetection=false'

        print("Web browsing URL: "+self.url, flush=True)

    def browse(self, driver):
        # Validate MOTD
        try:
            element = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.CSS_SELECTOR,"#motd_do_not_show_again")))
            element.click()
        except Exception as e:
            print("MOTD not found", flush=True)

        # Accept Cookies
        try:
            element = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.CSS_SELECTOR,"#cookie_footer > section > section > section > a")))
            element.click()
        except Exception as e:
            print("Cookies banner not found", flush=True)

