import sys
import os
import importlib
import inspect
import json
import time
import queue
import traceback
from selenium import webdriver
from selenium.webdriver.chrome.service import Service

class IVR:
    def __init__(self, width=None, height=None, 
                 room=None, name=None, browsing=None):
        self.url = ''
        self.browsing = browsing if browsing else ''
        self.room = room if room else ''
        self.name = name if name else ''
        self.width = width
        self.height = height
        self.driver = None
        self.browsingObj = None
        self.IVRTimeout = int(os.environ.get('IVR_TIMEOUT'))
        self.userInputs = queue.Queue()
        self.service = []
        self.chromeOptions = webdriver.ChromeOptions()
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
        if os.environ.get('WITH-ALSA') == "true":
            self.chromeOptions.add_argument('--alsa-input-device=hw:1,1')
            self.chromeOptions.add_argument('--alsa-output-device=hw:0,0')
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
        if self.room:
            self.url = '{}&roomId={}'.format(self.url, self.room)
        if self.browsing:
            self.url = '{}&domainKey={}'.format(self.url, self.browsing)
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
        browsing = ''
        while True:
            if self.IVRTimeout and time.time() > ( startTime + self.IVRTimeout ):
                print("IVR Timeout", flush=True)
                return {}
            try:
                if not browsing:
                    browsing = self.driver.execute_script("return window.browsing")
                else:
                    room = self.driver.execute_script("return window.room")
                    if room:
                        print("IVR: browsing, room: {}, {}".format(browsing, room['roomName']), flush=True)
                        return browsing, room
                self.interact()
            except Exception as e:
                traceback.print_exc(file=sys.stdout)
                print("IVR error: {}".format(e), flush=True)
                return {}

    def attend(self):
        sys.path.append("{}/../browsing".format(os.path.dirname(os.path.abspath(__file__))))
        modName = self.browsing
        print("Browsing mod name: " + modName, flush=True)
        mod = importlib.import_module(modName)
        isClassMember = lambda member: inspect.isclass(member) and member.__module__ == modName
        browsingClass = inspect.getmembers(mod, isClassMember)
        if not browsingClass:
            raise ImportError(f"No class found in {modName}")
        browsingObj = browsingClass[0][1]
        self.browsingObj = browsingObj(self.width, self.height, self.config,
                                       self.browsing, self.room, self.name,
                                       self.driver, self.userInputs)
        self.browsingObj.run()

    def run(self):
        self.launchBrowser()
        try:
            browsing, room = self.prompt()
            self.room = room
            self.browsing = browsing.lower().replace(" ", "")
            self.attend()
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
            print("IVR error: {}".format(e), flush=True)
            return {}