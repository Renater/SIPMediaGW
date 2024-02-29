#!/usr/bin/python

import web
import json
import re
import subprocess
import os

allowedToken = 1234

class Launcher:
    def GET(self, args=None):
        auth = web.ctx.env.get('HTTP_AUTHORIZATION')
        authReq = False
        if auth is None:
            authReq = True
        else:
            auth = re.sub('^Bearer ', '', auth)
            if authReq != allowedToken:
                authReq = True
        if not authReq:
            data = web.input()
            resJson = []
            web.header('Content-Type', 'application/json')
            response = dict()
            gwSubProc = ['./SIPMediaGW.sh']
            if 'from' in data.keys():
                gwSubProc.append( '-f%s' % data['from'])
            if 'room' in data.keys() and data['room'] != '0':
                gwSubProc.append( '-r%s' % data['room'])
            if 'prefix' in data.keys():
                gwSubProc.append( '-p%s' % data['prefix'])
            if 'domain' in data.keys():
                gwSubProc.append( '-d%s' % data['domain'])
            if 'rtmpDst' in data.keys():
                gwSubProc.append( '-u%s' % data['rtmpDst'])
            filePath = os.path.dirname(__file__)
            print(gwSubProc)
            res = subprocess.Popen(gwSubProc, cwd=filePath, stdout=subprocess.PIPE)
            res.wait()
            resStr = res.stdout.read().decode('utf-8')
            resJson = json.loads(resStr.replace("'", '"'))

            return json.dumps(resJson)
        else:
            web.header('WWW-Authenticate', 'Bearer error="invalid_token"')
            web.ctx.status = '401 Unauthorized'
            return

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

urls = "/(.*)", "Launcher"
application = web.application(urls, globals()).wsgifunc()

urls = ("/sipmediagw", "Launcher",
    "/chat", "Chat")


app = web.application(urls, globals())
if __name__ == "__main__":
    app.run()
