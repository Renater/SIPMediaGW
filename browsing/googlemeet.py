#!/usr/bin/env python

import sys
import os
import traceback
from browsing import Browsing
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class Googlemeet(Browsing):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Hide Chromium headless/automation fingerprint from Google Meet
        if self.chromeOptions:
            self.chromeOptions.add_argument(
                '--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 '
                '(KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36'
            )
            self.chromeOptions.add_argument('--disable-blink-features=AutomationControlled')

    def loadPage(self):
        # Navigate to Google Meet room — URL format: meet.google.com/xxx-yyyy-zzz
        self.driver.get("https://{}/{}".format(
            self.room['config']['webrtc_domain'],
            self.room['roomName']
        ))

        # Hide navigator.webdriver property (checked by Google)
        try:
            self.driver.execute_script(
                "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
            )
        except Exception:
            pass

        # Dismiss cookie consent popup if present (incognito / first launch)
        try:
            consent_btn = WebDriverWait(self.driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "div.TZFSLb button"))
            )
            consent_btn.click()
            print("Google Meet: consent popup dismissed", flush=True)
        except Exception:
            pass

        # Wait for the prejoin screen — use aria-label (stable, #cXX ID is dynamic)
        try:
            WebDriverWait(self.driver, 60).until(
                EC.presence_of_element_located((By.CSS_SELECTOR,
                    "input[aria-label='Votre nom'], input[aria-label='Your name']"
                ))
            )
        except Exception:
            print("Google Meet: name input not found, continuing anyway", flush=True)

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
