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
import urllib.parse

class BBBESR (Browsing):

    def loadPage(self):
        self.driver.get("http://{}".format(
            urllib.parse.unquote(self.room['roomName']).lstrip("/").replace('https://','')
        ))
        # try:
        #     if 'classe-virtuelle.numerique-esr.fr' in self.driver.current_url:
        #         classroomBtn = WebDriverWait(self.driver, 20).until(
        #             EC.element_to_be_clickable(
        #                 (By.CSS_SELECTOR, 'button.c__button--primary[aria-label="Click here to access classroom"], button.c__button--primary')
        #             )
        #         )
        #         classroomBtn.click()
        #         preJoinRoomBtn = WebDriverWait(self.driver, 1).until(
        #             EC.element_to_be_clickable(
        #                 (By.CSS_SELECTOR, 'button.c__button--primary[aria-label="Click here to access classroom"], button.c__button--primary')
        #             )
        #         )
        #         if preJoinRoomBtn:
        #             preJoinRoomBtn.click()

        # except Exception as error:
        #     print(f"[✗] Prejoin process failed: {error}", flush=True)

    def join(self):
        self.loadJS(os.path.join(os.path.dirname(os.path.normpath(__file__)),'./assets/uihelper.js'))
        self.loadJS(os.path.join(os.path.dirname(os.path.normpath(__file__)),'./assets/bbbesr.js'))
        self.driver.execute_script(self.initScript)
        preJoinTab = self.driver.execute_script("return window.meeting.preJoin();")
        super().join()
        handlesBefore = set(self.driver.window_handles)
        if preJoinTab:
            WebDriverWait(self.driver, 10).until(
                lambda d: len(set(d.window_handles) - handlesBefore) > 0
            )
            newTabHandle = list(set(self.driver.window_handles) - handlesBefore)[0]
            self.driver.switch_to.window(newTabHandle)
        try:
            WebDriverWait(self.driver, 10).until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, '[data-test="audioModal"]')
                    )
                )
        except:
            print("Cannot enter meeting", flush=True)
            return

        self.loadJS(os.path.join(os.path.dirname(os.path.normpath(__file__)),'./assets/uihelper.js'))
        self.loadJS(os.path.join(os.path.dirname(os.path.normpath(__file__)),'./assets/bbbesr.js'))
        self.driver.execute_script(self.initScript)
        self.driver.execute_script("window.meeting.browse();")

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