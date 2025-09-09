#!/usr/bin/env python

import sys
import time
import os
import json
import time
from browsing import Browsing
import traceback


class Jitsi (Browsing):

    def chatHandler(self):
        try:
            message = self.chatMsg.get(True, 0.01).strip()
            chatCmd = "window.jitsiApiClient.executeCommand('sendChatMessage', '{}')".format(message)
            self.driver.execute_script(chatCmd)
        except Exception as e:
            pass

    def join(self):
        super().join()
        try:
            self.driver.switch_to.default_content()
            jitsiUrl = self.driver.execute_script("return window.jitsiApiClient._url;")
            print("Jitsi URL: "+jitsiUrl, flush=True)
        except Exception as e:
            print("Iframe to defaut content switching error", flush=True)
            try:
                jitsiUrl = self.driver.execute_script("return window.location.href;")
            except:
                return
            print("Jitsi URL: "+jitsiUrl, flush=True)

    def unset(self):
        try:
            self.driver.execute_script(
                "if ( jitsi ) { jitsi.leave(); }"
            )
        except Exception as e:
            traceback.print_exc(file=sys.stdout)
            print("Meeting logout error: {}".format(e), flush=True)

