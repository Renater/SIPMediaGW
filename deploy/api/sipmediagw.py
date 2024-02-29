#!/usr/bin/python

import web
import json
import re
import subprocess
import os

allowedToken = 1234

class Chat:
    def POST(self):
        data = json.loads(web.data().decode("utf-8"))#web.input()#data().decode("utf-8")
        if 'room' in data:
            room = data['room']
        if 'msg' in data:
            msg = data['msg']
        msgDict = '{{"event":"message", "type":"CHAT_INPUT", "text": "{}" }}'.format(msg)
        msgDict = msgDict.replace('\n', '\\n')
        subprocess.run(['echo "{}" | netcat -q 1 {} 4444'.format(msgDict, room)],
             shell=True)

urls = ("/chat", "Chat")
application = web.application(urls, globals()).wsgifunc()

app = web.application(urls, globals())
if __name__ == "__main__":
    app.run()
