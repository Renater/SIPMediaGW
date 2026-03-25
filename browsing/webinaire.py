#!/usr/bin/env python
import time
import os
import sys
import json
import traceback
from browsing import Browsing
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class Webinaire(Browsing):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Keep Chrome security policy aligned with BigBlueButton new-ui behavior.
        if '--disable-web-security' in self.chromeOptions.arguments:
            self.chromeOptions.arguments.remove('--disable-web-security')
            print(">>> Removed '--disable-web-security' from Chrome options", flush=True)

    def loadPage(self):
        self.token = self.room['config']['auth_token']['webinaire_token']
        self.driver.execute_cdp_cmd("Network.enable", {})
        self.driver.execute_cdp_cmd(
            "Network.setExtraHTTPHeaders",
            {"headers": {"Authorization": self.token}}
        )

        self.driver.get("https://{}/{}".format(
            self.room['config']['webrtc_domain'],
            self.room['roomName']
        ))

    def join(self):
        super().join()
        try:
            WebDriverWait(self.driver, 10).until(EC.url_contains("sessionToken"))
        except:
            print("Cannot enter meeting", flush=True)
            return

        self.loadJS(os.path.join(os.path.dirname(os.path.normpath(__file__)), './assets/uihelper.js'))
        self.loadJS(os.path.join(os.path.dirname(os.path.normpath(__file__)), './assets/webinaire.js'))
        self.driver.execute_script(self.initScript)
        self.driver.execute_script("""
            if (window.meeting) {
                window.meeting.joined = true;
                window.meeting.browse();
            }
        """)

    def chatHandler(self):
        try:
            message = self.chatMsg.get(True, 0.02)
            self.driver.execute_script('bbb.typeText("{}")'.format(message))
        except Exception as e:
            pass

    def unset(self):
        try:
            self.driver.execute_script(
                "if ( window.meeting ) { window.meeting.leave(); }"
            )
            # Waiting for the leaveMeetingDropdown button to disappear (max 10s)
            WebDriverWait(self.driver, 10).until(
                EC.invisibility_of_element_located((By.CSS_SELECTOR, '[data-test="leaveMeetingDropdown"]'))
            )
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
            print("Meeting logout error: {}".format(e), flush=True)