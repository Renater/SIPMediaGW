#!/usr/bin/env python

import sys
import os
import traceback
import queue
import base64
import time
import threading
import subprocess

class Browsing:
    def __init__(self, width, height, config,
                 modName=None, room=None, name=None,
                 driver=None, inputs=None):
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
        self.driver = driver
        self.chatMsg = queue.Queue()

    def loadJS(self, jsScript):
        with open(jsScript, "r", encoding="utf-8") as f:
            js_code = f.read()
        self.driver.execute_script(js_code)

    def loadImages(self, path, lang):
        with open(path + "icon.png", "rb") as f:
            self.iconB64 = "data:image/png;base64,{}".format(base64.b64encode(f.read()).decode("utf-8"))
        with open( path + "dtmf_{}.png".format(lang), "rb") as f:
            self.dtmfB64 = "data:image/png;base64,{}".format(base64.b64encode(f.read()).decode("utf-8"))

    def loadPage(self):
        pass

    def join(self):
        self.loadJS(os.path.join(os.path.dirname(os.path.normpath(__file__)),
                                 '../browsing/assets/{}.js'.format(self.modName)))
        self.initScript = "window.meeting = new window.Browsing('{}', '{}', '{}', '{}', '{}')".format(
                                                    self.room['config']['webrtc_domain'],
                                                    self.room['roomName'],
                                                    self.room['displayName'],
                                                    self.room['config']['lang'],
                                                    self.room['roomToken'])
        self.driver.execute_script(self.initScript)
        self.driver.execute_script("window.meeting.join();")

    def monitorSingleParticipant(self, thresholdSeconds=300, checkInterval=60):
        singleStartTime = None
        def checkLoop():
            nonlocal singleStartTime
            while True:
                try:
                    participantNum = self.driver.execute_script("return window.meeting.getParticipantNum()")
                except Exception as e:
                    print(f"Error getting participant number: {e}", flush=True)
                    participantNum = None

                if participantNum <= 1:
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

    def chatHandler(self):
        pass

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
            self.loadPage()
            self.join()
            if os.getenv("ENDING_TIMEOUT"):
                self.monitorSingleParticipant(int(os.getenv("ENDING_TIMEOUT")), checkInterval=60)
            self.loadImages(os.path.join(os.path.dirname(os.path.normpath(__file__)),'../browsing/assets/'),
                            self.config['lang'])
            menuScript = "menu=new Menu(); \
                        menu.img['icon'] = '{}'; \
                        menu.img['dtmf'] = '{}'; \
                        menu.show();".format(self.iconB64, self.dtmfB64)
            self.loadJS(os.path.join(os.path.dirname(os.path.normpath(__file__)),'../browsing/assets/IVR/menu.js'))
            self.driver.execute_script(menuScript)
            while self.room:
                self.interact()
                self.chatHandler()
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


