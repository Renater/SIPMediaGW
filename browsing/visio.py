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
        self.slideSelector = self.driver.execute_script("return window.meeting.slideSelector;")
        def unpinSlide(maxRetries=2):
            try:
                while self.driver:
                    for attempt in range(maxRetries + 1):
                        try:
                            videoElement = self.driver.find_element(By.CSS_SELECTOR, self.slideSelector)
                            ActionChains(self.driver).move_to_element(videoElement).perform()
                            self.driver.execute_script("if(meeting.unpinSlide){meeting.unpinSlide();}")
                            break

                        except NoSuchElementException:
                            break

                        except StaleElementReferenceException:
                            if attempt == maxRetries:
                                break  # next polling will catch the new element
                            continue  # DOM changed between, let's retry with a fresh find_element

                        except NoSuchWindowException:
                            pass

                        except Exception as e:
                            print("Error in unpinSlide thread: {}".format(e), flush=True)

                    time.sleep(checkInterval)
            except Exception as e:
                print("Error in unpinSlide thread: {}".format(e), flush=True)

        thread = threading.Thread(target=unpinSlide, daemon=True)
        thread.start()

    def unset(self):
        try:
            self.driver.execute_script(
                "if ( window.meeting ) { window.meeting.leave(); }"
            )
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
            print("Meeting logout error: {}".format(e), flush=True)

