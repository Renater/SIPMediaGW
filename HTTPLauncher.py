#!/usr/bin/python

import web
import json
import re
import subprocess
import os

allowedToken = '1234'

def authorize(func):
    def inner(*args, **kwargs):
        auth = web.ctx.env.get('HTTP_AUTHORIZATION')
        authReq = False
        if auth is None:
            authReq = True
        else:
            auth = re.sub('^Bearer ', '', auth)
            if auth != allowedToken:
                authReq = True
        if not authReq:
            return func(*args, **kwargs)
        else:
            web.header('WWW-Authenticate', 'Bearer error="invalid_token"')
            web.ctx.status = '401 Unauthorized'
            return 'authorization error'
    return inner

class Start:
    @authorize
    def GET(self, args=None):
        data = web.input()
        resJson = []
        web.header('Content-Type', 'application/json')
        gwSubProc = ['./SIPMediaGW.sh']
        if 'room' in data.keys() and data['room'] != '0':
            gwSubProc.append( '-r%s' % data['room'])
        else:
            return '{"Error": "a room name must be specified"}'
        if 'from' in data.keys():
            gwSubProc.append( '-f%s' % data['from'])
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

class Stop:
    @authorize
    def GET(self, args=None):
        data = web.input()
        resJson = []
        web.header('Content-Type', 'application/json')
        gwSubProc = ['docker', 'compose']
        if 'room' in data.keys() and data['room'] != '0':
            gwSubProc.append( '-p%s' % data['room'])
        else:
            return '{"Error": "a room name must be specified"}'
        gwSubProc.append( 'down')
        filePath = os.path.dirname(__file__)
        print(gwSubProc)
        res = subprocess.Popen(gwSubProc, cwd=filePath, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        res.wait()
        resStr = res.stderr.read().decode('utf-8')
        retStr = ''
        lines = resStr.splitlines()
        for line in lines:
            if 'level=warning' not in line:
                if retStr:
                    retStr += ' => '
                retStr += line
        resJson = {'res': retStr}

        return json.dumps(resJson)

class Chat:
    def forwardCommand(self, inDict, room):
        msgSubProc = ['docker', 'compose', 'run', '--rm', '--entrypoint', '/bin/sh', 'gw', '-c']
        msgSubProc.append( "echo '{}' | netcat -q 1 {} 4444".format(inDict, room) )
        filePath = os.path.dirname(__file__)
        print(msgSubProc)
        res = subprocess.Popen(msgSubProc, cwd=filePath, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        res.wait()
        resStr = res.stderr.read().decode('utf-8')
        retStr = ''
        lines = resStr.splitlines()
        for line in lines:
            if 'level=warning' not in line:
                if retStr:
                    retStr += ' => '
                retStr += line
        if retStr:
            resJson = {'res': retStr}
        else:
            resJson = {'res': 'ok'}
        return json.dumps(resJson)

    @authorize
    def GET(self, args=None):
        data = web.input()
        web.header('Content-Type', 'application/json')
        if 'room' in data.keys():
            room = data['room']
        else:
            return '{"Error": "a room name must be specified"}'
        if 'toggle' in data.keys():
            action = 'toggle'
        else:
            return '{"Error": "toggle parameter is expected"}'
        actDict = '{{"event":"action", "type":"CHAT_INPUT", "action": "{}" }}'.format(action)
        actDict = actDict.replace('\n', '\\n')
        return self.forwardCommand(actDict, room)

    def POST(self):
        data = json.loads(web.data().decode("utf-8"))
        web.header('Content-Type', 'application/json')
        if 'room' in data:
            room = data['room']
        else:
            return '{"Error": "a room name must be specified"}'
        if 'msg' in data:
            msg = data['msg']
        else:
            return '{"Error": "message missing or not readable"}'
        msgDict = '{{"event":"message", "type":"CHAT_INPUT", "text": "{}" }}'.format(msg)
        msgDict = msgDict.replace('\n', '\\n')
        return self.forwardCommand(msgDict, room)


urls = ("/start", "Start",
        "/stop", "Stop",
        "/chat", "Chat")

application = web.application(urls, globals()).wsgifunc()

app = web.application(urls, globals())
if __name__ == "__main__":
    app.run()
