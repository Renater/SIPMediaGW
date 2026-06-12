#!/usr/bin/env python

import sys
import os
import select
import traceback
import queue
import base64
import json
import time
import threading
import subprocess
from selenium import webdriver

class Browsing:
    def __init__(self, width, height, config,
                 modName=None, room=None, name=None,
                 service=None, chromeOptions=None,
                 inputs=None, readPairingCode=None):
        self.url = ''
        self.room = room if room else {}
        self.name = name if name else ''
        self.width = width
        self.height = height
        self.config = config
        self.modName =  modName
        self.initScript = ''
        self.screenShared = False
        self.userInputs = inputs
        self.readPairingCode = readPairingCode
        self.service = service
        self.chromeOptions = chromeOptions
        if os.environ.get('AUDIO_ONLY') == "true":
            self.chromeOptions.add_argument('--headless=new')
            self.chromeOptions.add_argument('--use-fake-ui-for-media-stream')
        self.chatFifo = "./chatFifo"
        if not os.path.exists(self.chatFifo):
            os.mkfifo(self.chatFifo)
        self.driver = None

    def loadJS(self, jsScript):
        cssPath = os.path.join(os.path.dirname(__file__),
                               "../browsing/assets/IVR/style.css")
        self.driver.execute_script(f"window.cssPath = 'file://{cssPath}';")
        with open(jsScript, "r", encoding="utf-8") as f:
            jsScript = f.read()
        self.driver.execute_script(jsScript)

    def loadImages(self, path, lang):
        with open(os.path.join(path, "icon.png"), "rb") as f:
            self.iconB64 = "data:image/png;base64," + base64.b64encode(f.read()).decode("utf-8")

        with open(os.path.join(path, f"dtmf_{lang}.png"), "rb") as f:
            self.dtmfB64 = "data:image/png;base64," + base64.b64encode(f.read()).decode("utf-8")

        icons_path = os.path.join(path, "IVR/images/menu-icons")
        icons = {}

        for filename in os.listdir(icons_path):
            if not filename.lower().endswith(".png"):
                continue

            key = os.path.splitext(filename)[0]
            file_path = os.path.join(icons_path, filename)

            with open(file_path, "rb") as f:
                icons[key] = (
                    "data:image/png;base64,"
                    + base64.b64encode(f.read()).decode("utf-8")
                )

        self.menuIcons = icons


    def loadPage(self):
        pass

    def join(self):
        self.loadJS(os.path.join(os.path.dirname(os.path.normpath(__file__)),
                                 '../browsing/assets/uihelper.js'))
        self.loadJS(os.path.join(os.path.dirname(os.path.normpath(__file__)),
                                 '../browsing/assets/{}.js'.format(self.modName)))
        self.initScript = "window.meeting = new window.Browsing('{}', '{}', '{}', '{}', '{}', '{}')".format(
                                                    self.room['config']['webrtc_domain'],
                                                    self.room['roomName'],
                                                    self.room['displayName'],
                                                    self.room['config']['lang'],
                                                    json.dumps(self.room['config']['ivr_prompts']),
                                                    self.room['roomToken'],
                                                    os.environ.get('AUDIO_ONLY'))
        self.driver.execute_script(self.initScript)
        self.driver.execute_script("window.meeting.join();")

    def monitorSingleParticipant(self, thresholdSeconds=300, checkInterval=60):
        singleStartTime = None
        def checkLoop():
            nonlocal singleStartTime
            while self.driver.execute_script("return('getParticipantNum' in window.meeting)"):
                try:
                    participantNum = self.driver.execute_script("return window.meeting.getParticipantNum()")
                except Exception as e:
                    print(f"Error getting participant number: {e}", flush=True)
                    participantNum = None

                if participantNum  and participantNum <= 1:
                    if singleStartTime is None:
                        singleStartTime = time.time()
                    elif time.time() - singleStartTime >= thresholdSeconds:
                        print(f"Single participant detected for {thresholdSeconds} seconds.", flush=True)
                        subprocess.run(['echo "/quit" | netcat -q 1 127.0.0.1 5555'], shell=True)
                        break
                else:
                    singleStartTime = None

                time.sleep(checkInterval)

        thread = threading.Thread(target=checkLoop, daemon=True)
        thread.start()
        return thread

    def browse(self):
        pass

    def chatHandler(self, timeout):
        fd = os.open(self.chatFifo, os.O_RDONLY | os.O_NONBLOCK)
        try:
            ready, _, _ = select.select([fd], [], [], timeout)
            if not ready:
                raise TimeoutError()
            data = os.read(fd, 4096)
            if data:
                self.driver.execute_script(
                    "window.meeting.sendChat(arguments[0]);",
                    data.decode().strip()
                )
                self.driver.execute_script("window.meeting.sendChat({});".format(json.dumps(data.strip())))
        finally:
            os.close(fd)
            return

    def interact(self):
        try:
            inKey = self.userInputs.get(True, 0.02)
        except Exception as e:
            return
        self.driver.execute_script(f"document.dispatchEvent(new KeyboardEvent('keydown',{{'key':'{inKey}'}}));")

    def unset(self):
        pass

    def run(self):
        try:
            self.driver = webdriver.Chrome(service=self.service,
                                           options=self.chromeOptions)
            self.loadPage()
            self.join()
            while True:
                joined = self.driver.execute_script("return window.meeting.joined")
                if joined:
                    break
                self.interact()
            if os.getenv("ENDING_TIMEOUT"):
                self.monitorSingleParticipant(int(os.getenv("ENDING_TIMEOUT")), checkInterval=60)
            self.loadImages(os.path.join(os.path.dirname(os.path.normpath(__file__)),'../browsing/assets/'),
                            self.config['lang'])

            menuScript = "menu=new Menu({}, {}); \
                          menu.img['icon'] = '{}'; \
                          menu.img['dtmf'] = '{}'; \
                          menu.img['icons'] = {}; \
                          menu.show();".format(
                            json.dumps(self.room['config']['menus'][self.modName]),
                            json.dumps(self.room['config']['lang']),
                            self.iconB64, self.dtmfB64, json.dumps(self.menuIcons))
            self.loadJS(os.path.join(os.path.dirname(os.path.normpath(__file__)),'../browsing/assets/IVR/menu.js'))
            self.driver.execute_script(menuScript)
            self.readPairingCode(self.driver)

            while self.room:
                self.interact()
                self.readPairingCode(self.driver)
                self.chatHandler(0.01)
        except Exception as e:
            print("Error while browsing: {}".format(e), flush=True)

    def stop(self):
        try:
            self.room={}
            self.name=''
            if self.driver:
                if self.driver.execute_script("return window.meeting"):
                    self.unset()
                self.driver.close()
                self.driver.quit()
                self.driver = []
                print("Browsing stopped", flush=True)
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
