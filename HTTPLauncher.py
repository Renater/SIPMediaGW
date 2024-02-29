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

urls = ("/launcher", "Launcher")
application = web.application(urls, globals()).wsgifunc()

app = web.application(urls, globals())
if __name__ == "__main__":
    app.run()
