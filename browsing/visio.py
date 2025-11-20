#!/usr/bin/env python

import sys
import time
import os
import json
import time
from browsing import Browsing
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support import expected_conditions as EC
import traceback


class Visio (Browsing):

    def loadPage(self):
        self.driver.get("https://{}/{}".format(
            self.room['config']['webrtc_domain'],
            self.room['roomName']
        ))
        WebDriverWait(self.driver, 60).until(
            EC.presence_of_element_located((By.TAG_NAME, "video"))
        )

    def chatHandler(self):
        pass

    def unset(self):
        try:
            self.driver.execute_script(
                "if ( window.meeting ) { window.meeting.leave(); }"
            )
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
            print("Meeting logout error: {}".format(e), flush=True)

