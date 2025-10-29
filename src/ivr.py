import sys
import os
import importlib
import inspect
import json
import time
import queue
import traceback
import urllib.parse
from selenium import webdriver
from selenium.webdriver.chrome.service import Service

class IVR:
    def __init__(self, width=None, height=None, 
                 roomName=None, name=None,
                 browsingId=None, browsingName=None,
                 mixedId=None):
        self.url = ''
        self.browsingId = browsingId if browsingId else ''
        self.mixedId = mixedId if mixedId else ''
        self.browsingName = browsingName if browsingName else ''
        self.roomName = roomName if roomName else ''
        self.name = name if name else ''
        self.width = width
        self.height = height
        self.driver = None
        self.browsingObj = None
        self.IVRTimeout = int(os.environ.get('IVR_TIMEOUT')) if os.environ.get('IVR_TIMEOUT') else None
        self.userInputs = queue.Queue()
        self.service = []
        self.chromeOptions = webdriver.ChromeOptions()
        if os.environ.get('AUDIO_ONLY') == "true":
            self.chromeOptions.add_argument('--headless=new')
            self.chromeOptions.add_argument('--use-fake-ui-for-media-stream')
        self.chromeOptions.add_argument('--no-sandbox')
        self.chromeOptions.add_argument('--disable-web-security')
        self.chromeOptions.add_argument('--disable-site-isolation-trials')
        self.chromeOptions.add_argument('--auto-select-desktop-capture-source=Screen 2')
        self.chromeOptions.add_argument('--screen-capture-audio-default-unchecked')
        self.chromeOptions.add_argument('--enable-usermedia-screen-capturing')
        self.chromeOptions.add_argument('--disable-gpu')
        self.chromeOptions.add_argument('--start-fullscreen')
        self.chromeOptions.add_argument('--kiosk')
        self.chromeOptions.add_argument('--window-size='+str(width)+','+str(height))
        self.chromeOptions.add_argument('--window-position=0,0')
        self.chromeOptions.add_argument('--hide-scrollbars')
        self.chromeOptions.add_argument('--disable-notifications')
        self.chromeOptions.add_argument('--autoplay-policy=no-user-gesture-required')
        self.chromeOptions.add_experimental_option("excludeSwitches", ['enable-automation', 'test-type'])
        self.chromeOptions.add_experimental_option('prefs',{'profile.default_content_setting_values.media_stream_mic':1,
                                                            'profile.default_content_setting_values.media_stream_camera':1})
        try:
            policyFile = "/etc/opt/chrome/policies/managed/managed_policies.json"
            os.makedirs(os.path.dirname(policyFile), exist_ok=True)
            with open(policyFile, "w") as f:
                f.write('{ "CommandLineFlagSecurityWarningsEnabled": false }')
            f.close()
        except:
            pass

    def setUrl(self):
        configFile = os.path.join(os.path.dirname(os.path.normpath(__file__)), '../browsing/assets/config.json')
        with open(configFile) as f:
            self.config = json.load(f)
        IVRPath = "file://"
        IVRPath += os.path.join(os.path.dirname(os.path.normpath(__file__)), '../browsing/assets/IVR/index.html')
        self.url = '{}?displayName={}'.format(IVRPath, self.name)
        if self.roomName:
            self.url = '{}&roomId={}'.format(self.url, self.roomName)
        if self.browsingId:
            self.url = '{}&domainId={}'.format(self.url, self.browsingId)
        if self.browsingName:
            self.url = '{}&domainKey={}'.format(self.url, self.browsingId)
        if self.mixedId:
            self.url = '{}&mixedId={}'.format(self.url, urllib.parse.quote(self.mixedId))
        print("Web browsing URL: "+self.url, flush=True)

    def launchBrowser(self):
        try:
            self.setUrl()
            if not self.url:
                return
            self.service = Service(executable_path='/usr/bin/chromedriver')
            self.driver = webdriver.Chrome(service=self.service,
                                           options=self.chromeOptions)
            self.driver.get(self.url)
            return
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
            return

    def interact(self):
            try:
                inKey = self.userInputs.get(True, 0.02)
            except Exception as e:
                return
            self.driver.execute_script(f"document.dispatchEvent(new KeyboardEvent('keydown',{{'key':'{inKey}'}}));")

    def prompt(self):
        startTime = time.time()
        browsingName = ''
        while True:
            if self.IVRTimeout and time.time() > ( startTime + self.IVRTimeout ):
                print("IVR Timeout", flush=True)
                return {}
            try:
                if not browsingName:
                    browsingName = self.driver.execute_script("return window.browsing")
                else:
                    room = self.driver.execute_script("return window.room")
                    if room:
                        print("IVR: browsing, room: {}, {}".format(browsingName, room['roomName']), flush=True)
                        return browsingName, room
                self.interact()
            except Exception as e:
                traceback.print_exc(file=sys.stdout)
                print("IVR error: {}".format(e), flush=True)
                return {}

    def attend(self, room):
        sys.path.append("{}/../browsing".format(os.path.dirname(os.path.abspath(__file__))))
        modName = self.browsingName
        print("Browsing mod name: " + modName, flush=True)
        mod = importlib.import_module(modName)
        isClassMember = lambda member: inspect.isclass(member) and member.__module__ == modName
        browsingClass = inspect.getmembers(mod, isClassMember)
        if not browsingClass:
            raise ImportError(f"No class found in {modName}")
        browsingObj = browsingClass[0][1]
        self.browsingObj = browsingObj(self.width, self.height, self.config,
                                       self.browsingName, room, self.name,
                                       self.service, self.chromeOptions,
                                       self.userInputs)
        self.browsingObj.run()

    def run(self):
        self.launchBrowser()
        try:
            browsingName, room = self.prompt()
            self.roomName = room['roomName'] if room and 'roomName' in room else ''
            self.browsingName = browsingName.lower().replace(" ", "")
            # Close IVR:
            self.driver.close()
            self.driver.quit()
            # Start Meeting:
            self.attend(room)
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
            print("IVR error: {}".format(e), flush=True)
            return {}