#!/usr/bin/env python

import sys
import traceback
import queue
import base64

class Browsing:
    def __init__(self, width, height, config,
                 room=None, name=None,
                 driver=None, inputs=None):
        self.url = ''
        self.room = room if room else {}
        self.name = name if name else ''
        self.width = width
        self.height = height
        self.config = config
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

    def browse(self):
        pass

    def interact(self):
        try:
            inKey = self.userInputs.get(True, 0.02)
        except Exception as e:
            return
        self.driver.execute_script(f"document.dispatchEvent(new KeyboardEvent('keydown',{{'key':'{inKey}'}}));")

    def unset(self):
        pass

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


