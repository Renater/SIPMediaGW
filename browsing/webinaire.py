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

class Webinaire (Browsing):

    def loadPage(self):
        self.driver.get("https://{}".format(
            self.room['config']['webrtc_domain']
        ))
        try:
            WebDriverWait(self.driver, 10).until(EC.url_contains("home"))

            roomCode = self.room['roomName']
            codeParts = [roomCode[:3], roomCode[3:6], roomCode[6:9]]

            for idx, part in enumerate(codeParts, start=1):
                inputElem = WebDriverWait(self.driver, 20).until(
                    EC.element_to_be_clickable((By.CSS_SELECTOR, f"#visio-code{idx}"))
                )
                inputElem.clear()
                inputElem.send_keys(part)

            # Click the submit button after filling the codes
            submitButton = WebDriverWait(self.driver, 10).until(
                EC.element_to_be_clickable((By.ID, "submit-visio-code"))
            )
            submitButton.click()

            # Switch to the new tab if one was opened
            WebDriverWait(self.driver, 10).until(lambda d: len(d.window_handles) > 1)
            newTabHandle = [h for h in self.driver.window_handles if h != self.driver.current_window_handle][0]
            self.driver.switch_to.window(newTabHandle)
        except:
            print("Cannot enter visio code", flush=True)
            return

    def join(self):
        super().join()
        try:
            WebDriverWait(self.driver, 10).until(EC.url_contains("sessionToken"))
        except:
            print("Cannot enter meeting", flush=True)
            return

        self.loadJS(os.path.join(os.path.dirname(os.path.normpath(__file__)),'./assets/uihelper.js'))
        self.loadJS(os.path.join(os.path.dirname(os.path.normpath(__file__)),'./assets/webinaire.js'))
        self.driver.execute_script(self.initScript)
        self.driver.execute_script("window.meeting.joined=true")
        self.driver.execute_script("window.meeting.browse();")

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