import sys
import os
import importlib
import inspect
import json
import time
import queue
import traceback
import urllib.parse
import qrcode
import base64
import subprocess
import requests
from io import BytesIO
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait


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

    def readPairingCode(self, driver):
        try:
            pairingCode = ''
            with open('/etc/environment') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('PAIRING_CODE='):
                        pairingCode = line.split('=', 1)[1].strip().strip('"\'')
                        break
            lastPairingInfo = driver.execute_script("return window.pairingInfo;")
            if lastPairingInfo and lastPairingInfo.get('pairingCode') == pairingCode:
                return
            if os.getenv('GW_PROXY') and os.getenv('QR_CODE_URL') and pairingCode:
                reverse = os.getenv('GW_REVERSE_PROXY') or os.getenv('GW_PROXY')
                qrCodeUrl = os.getenv('QR_CODE_URL').format(
                    reverse_proxy=reverse,
                    code=pairingCode
                )
                pairingUrl = qrCodeUrl.split('?')[0]

                # Generate QR PNG as base64 (no data: prefix)
                try:
                    qr = qrcode.QRCode(box_size=4, border=2)
                    qr.add_data(qrCodeUrl)
                    qr.make(fit=True)
                    img = qr.make_image(fill_color="black", back_color="white")
                    buffered = BytesIO()
                    img.save(buffered, format="PNG")
                    qrB64 = base64.b64encode(buffered.getvalue()).decode("utf-8")
                except Exception:
                    qrB64 = ''

                pairingInfo = {
                    "pairingCode": pairingCode,
                    "qrCodeB64": qrB64,
                    "pairingUrl": pairingUrl
                }
            else:
                pairingInfo = { "pairingCode": "" }

            # inject safely as JS object
            try:
                driver.execute_script("window.pairingInfo = arguments[0];", pairingInfo)
                driver.execute_script("window.updateQrCode();")
                print("IVR: QR Code URL: {}".format(qrCodeUrl), flush=True)
                print("IVR: Pairing Code: {}, Pairing URL: {}".format(pairingCode, pairingUrl), flush=True)
            except Exception:
                # best-effort, ignore if driver not ready
                pass
        except Exception:
            pass

    def setUrl(self):
        configFile = os.path.join(os.path.dirname(os.path.normpath(__file__)), '../browsing/assets/config.json')
        with open(configFile) as f:
            self.config = json.load(f)
        self.applyBrowserLanguage(self.config.get("lang", "en"))
        IVRPath = "file://"
        IVRPath += os.path.join(os.path.dirname(os.path.normpath(__file__)), '../browsing/assets/IVR/index.html')
        self.url = '{}?displayName={}'.format(IVRPath, self.name)
        if self.roomName:
            self.url = '{}&roomId={}'.format(self.url, self.roomName)
        if self.browsingId:
            self.url = '{}&domainId={}'.format(self.url, self.browsingId)
        if self.browsingName:
            self.url = '{}&domainKey={}'.format(self.url, self.browsingName)
        if self.mixedId:
            self.url = '{}&mixedId={}'.format(self.url, urllib.parse.quote(self.mixedId))
        print("Web browsing URL: "+self.url, flush=True)

    def applyBrowserLanguage(self, lang):
        normalized = (lang or "en").strip().lower()
        locale_map = {
            "fr": "fr-FR",
            "en": "en-US",
            "es": "es-ES",
            "de": "de-DE",
            "it": "it-IT",
        }
        locale = locale_map.get(
            normalized,
            normalized if "-" in normalized else f"{normalized}-{normalized.upper()}",
        )

        self.chromeOptions.add_argument(f'--lang={locale}')
        prefs = self.chromeOptions.experimental_options.get('prefs', {})
        prefs['intl.accept_languages'] = f'{locale},{normalized}'
        self.chromeOptions.add_experimental_option('prefs', prefs)

    def launchBrowser(self):
        try:
            self.setUrl()
            if not self.url:
                return
            self.driver = webdriver.Remote(
                command_executor="http://127.0.0.1:9515",
                options=self.chromeOptions
            )
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
        jsScript = os.path.join(os.path.dirname(os.path.normpath(__file__)), '../browsing/assets/IVR/menu.js')
        with open(jsScript, "r", encoding="utf-8") as f:
            jsScript = f.read()
        self.driver.execute_script(jsScript)
        self.readPairingCode(self.driver)

        while True:
            if self.IVRTimeout and time.time() > ( startTime + self.IVRTimeout ):
                print("IVR Timeout", flush=True)
                return {}
            try:
                if not browsingName:
                    browsingName = self.driver.execute_script("return window.browsing")
                    if browsingName:
                        print("IVR: browsing: {}".format(browsingName), flush=True)
                else:
                    room = self.driver.execute_script("return window.room")
                    if room:
                        print("IVR: room: {}".format(room['roomName']), flush=True)
                        return browsingName, room
                self.interact()
                self.readPairingCode(self.driver)
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
                                       self.userInputs, self.readPairingCode)
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
