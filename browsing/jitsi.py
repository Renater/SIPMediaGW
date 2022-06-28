#!/usr/bin/env python

import sys
import time
import os
import requests
import json
from browsing import Browsing
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

jitsiFQDN = os.environ.get('WEBRTC_DOMAIN')
if not jitsiFQDN:
    jitsiFQDN = "rendez-vous.renater.fr"
confMapperPath = ""#"conf-api/conferenceMapper"

class Jitsi (Browsing):

    def getRoomName(self):
        reqUrl = ('https://{}/{}?id={}'.
                  format(jitsiFQDN, confMapperPath,self.room))
        print("ConfMapper request URL: "+reqUrl, flush=True)
        r = requests.get(reqUrl, verify=False)
        mapping = json.loads(r.content.decode('utf-8'))
        if 'conference' in mapping:
            return mapping['conference']
        elif 'error' in mapping:
            raise Exception(mapping['error'])
        else:
            return

    def setUrl(self):
        urlBase = ''
        try:
            if confMapperPath:
                urlConference = self.getRoomName().split('@')
                urlDomain = urlConference[1].split('conference.')[1]
                urlBase = 'https://{}/{}'.format(urlDomain, urlConference[0])
            else:
                urlBase =  'https://{}/{}'.format(jitsiFQDN, self.room)
        except Exception as exc:
            print("Failed to get room URL:", exc, flush=True)
            return

        self.url += urlBase
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

