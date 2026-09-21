#!/usr/bin/env python

import sys
import time
import threading
import time
from browsing import Browsing
from selenium.webdriver.common.by import By
from selenium.common.exceptions import NoSuchElementException, StaleElementReferenceException
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchWindowException
from selenium.common.exceptions import InvalidSessionIdException
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

    def dualScreenLayout(self, checkInterval=1):
        super().dualScreenLayout()

        thread = getattr(self, "_unpinSlideThread", None)
        if thread and thread.is_alive():
            return

        def setPinState(pinned: bool):
            method = "unpinSlide" if pinned else "pinSlide"
            return self.driver.execute_async_script(f"""
                const callback = arguments[arguments.length - 1];
                if (meeting.{method}) {{
                    meeting.{method}().then(callback);
                }} else {{
                    callback({{ok: false, reason: 'no-method'}});
                }}
            """)

        def unpinSlide(maxRetries=2):
            try:
                prevDualScreenOn = None
                while self.driver:
                    try:
                        dualScreenOn = self.driver.execute_script(
                            "return !!(window.meeting && window.meeting.dualScreenOn);"
                        )
                    except (NoSuchWindowException, InvalidSessionIdException):
                        break

                    # Only run the pin/unpin logic when the dualScreenOn value changed
                    if dualScreenOn != prevDualScreenOn:
                        for attempt in range(maxRetries + 1):
                            try:
                                videoElement = self.driver.find_element(By.CSS_SELECTOR, self.slideSelector)
                                ActionChains(self.driver).move_to_element(videoElement).perform()
                                togglePinSucceeded = setPinState(pinned=dualScreenOn)
                                print("Pin/unpin slide action performed. Dual screen on: {}, Pin status: {}".format(dualScreenOn, togglePinSucceeded), flush=True)
                                if togglePinSucceeded == True:
                                    prevDualScreenOn = dualScreenOn
                                    break

                            except NoSuchElementException:
                                break

                            except StaleElementReferenceException:
                                if attempt == maxRetries:
                                    break  # next polling will catch the new element
                                continue  # DOM changed between, let's retry with a fresh find_element

                            except (NoSuchWindowException, InvalidSessionIdException):
                                break  # Browser window closed, exit the loop

                            except Exception as e:
                                print("Error in unpinSlide thread: {}".format(e), flush=True)
                    time.sleep(checkInterval)
            except Exception as e:
                print("Error in unpinSlide thread: {}".format(e), flush=True)
            finally:
                self._unpinSlideThread = None

        if not self.driver or not self.driver.execute_script("return !!(window.meeting && window.meeting.dualScreenOn);"):
            return

        self._unpinSlideThread = threading.Thread(target=unpinSlide, daemon=True)
        self._unpinSlideThread.start()

    def unset(self):
        try:
            self.driver.execute_script(
                "if ( window.meeting ) { window.meeting.leave(); }"
            )
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
            print("Meeting logout error: {}".format(e), flush=True)

