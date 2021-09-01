#!/usr/bin/env python

import sys
import time
import traceback
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException

class Browsing:

    def __init__(self, room, name, width, height):
        self.url = ''
        self.room = room
        self.name = name
        self.width = width
        self.height= height
        self.chromeOptions = Options()
        self.chromeOptions.add_argument('--no-sandbox')
        self.chromeOptions.add_argument('--use-fake-ui-for-media-stream')
        self.chromeOptions.add_argument('--disable-dev-shm-usage')
        self.chromeOptions.add_argument('--disable-gpu')
        self.chromeOptions.add_argument('--start-fullscreen')
        self.chromeOptions.add_argument('--window-size='+width+','+height)
        self.chromeOptions.add_argument('--window-position=0,0')
        self.chromeOptions.add_argument('--hide-scrollbars')
        self.chromeOptions.add_argument('--disable-notifications')
        self.chromeOptions.add_argument('--disable-logging') 
        self.chromeOptions.add_argument("--log-level=3")
        self.chromeOptions.add_experimental_option("excludeSwitches", ['enable-automation']);

    def setUrl(self):
        pass

    def browse(self, driver):
        pass

    def run(self):
        try:
            driver = webdriver.Chrome('/usr/bin/chromedriver',options=self.chromeOptions, service_log_path='/dev/null')
            self.setUrl()
            driver.get(self.url)

            self.browse(driver)

            while True:
                time.sleep(1)
                try:
                    driver.title
                except WebDriverException:
                    break

            driver.quit()

        except Exception as e:
            traceback.print_exc(file=sys.stdout)

        print("All done!", flush=True)


