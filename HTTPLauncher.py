#!/usr/bin/python3

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
            return json.dumps({'Error': 'authorization error'})
    return inner

class Start:
    @authorize
    def GET(self, args=None):
        data = web.input()
        resJson = {}
        web.header('Content-Type', 'application/json')
        gwSubProc = ['./SIPMediaGW.sh']
        if 'room' in data.keys() and data['room'] != '0':
            gwSubProc.extend(['-r', data['room']])
        else:
            web.ctx.status = '400 Bad Request'
            return json.dumps({"Error": "a room name must be specified"})
        if 'from' in data:
            gwSubProc.extend(['-f', data['from']])
        if 'prefix' in data:
            gwSubProc.extend(['-p', data['prefix']])
        if 'domain' in data:
            gwSubProc.extend(['-w', data['domain']])
        if 'rtmpDst' in data:
            gwSubProc.extend(['-u', data['rtmpDst']])
        if 'dial' in data:
            gwSubProc.extend(['-d', data['dial']])
        if 'loop' in data and data['loop']:
            gwSubProc.append('-l')
        if 'transcript' in data and data['transcript']:
            gwSubProc.append('-s')
        if 'apiKey' in data:
            gwSubProc.extend(['-a', data['apiKey']])
        if 'userMail' in data:
            gwSubProc.extend(['-m', data['userMail']])

        filePath = os.path.dirname(__file__)
        print(gwSubProc)
        res = subprocess.Popen(gwSubProc, cwd=filePath, stdout=subprocess.PIPE)
        res.wait()
        resStr = res.stdout.read().decode('utf-8')
        resJson = json.loads(resStr.replace("'", '"'))

        web.ctx.status = '200 OK'
        return json.dumps({"status": "success", "details": resJson})

class Stop:
    @authorize
    def GET(self, args=None):
        data = web.input()
        resJson = {}
        web.header('Content-Type', 'application/json')
        if 'room' in data.keys() and data['room'] != '0':
            gwSubProc = ['docker', 'compose', 'ls','--format', 'json', '-q' ]
            res = subprocess.Popen(gwSubProc, cwd='.', stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            res.wait()
            resStr = res.stdout.read().decode('utf-8')
            projects=resStr.splitlines()
            if data['room'] in projects:
                gwSubProc = ['docker', 'compose']
                gwSubProc.extend(['-p', data['room']])
            else:
                web.ctx.status = '400 Bad Request'
                return json.dumps({"Error": "no running container for room={}".format(data['room'])})
        else:
            web.ctx.status = '400 Bad Request'
            return json.dumps({"Error": "a room name must be specified"})
        if 'force' in data.keys() and data['force']:
            gwSubProc.append('down')
        else:
            gwSubProc.append('stop')
            gwSubProc.append('gw')
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

        web.ctx.status = '200 OK'
        return json.dumps({"status": "success", "details": resJson})

class Chat:
    def forwardCommand(self, inDict, room):
        msgSubProc = ['docker', 'compose', 'run', '--rm', '--entrypoint', '/bin/sh', 'gw', '-c']
        msgSubProc.append("echo '{}:{},'| netcat -q 1 {} 4444".format(len(inDict),inDict, room))
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
            web.ctx.status = '400 Bad Request'
            return json.dumps({"Error": "a room name must be specified"})
        if 'toggle' in data.keys():
            action = 'toggle'
        else:
            web.ctx.status = '400 Bad Request'
            return json.dumps({"Error": "toggle parameter is expected"})
        actDict = '{{"event":"action", "type":"CHAT_INPUT", "action": "{}" }}'.format(action)
        actDict = actDict.replace('\n', '\\n')
        return self.forwardCommand(actDict, room)

    def POST(self):
        data = json.loads(web.data().decode("utf-8"))
        web.header('Content-Type', 'application/json')
        if 'room' in data:
            room = data['room']
        else:
            web.ctx.status = '400 Bad Request'
            return json.dumps({"Error": "a room name must be specified"})
        if 'msg' in data:
            msg = data['msg'].encode('utf-8')
        else:
            web.ctx.status = '400 Bad Request'
            return json.dumps({"Error": "message missing or not readable"})
        msgDict = '{{"event":"message", "type":"CHAT_INPUT", "text": "{}"}}'.format(msg)
        msgDict = msgDict.replace('\n', '\\n')
        msgDict = msgDict.replace("'",'\\"')
        return self.forwardCommand(msgDict, room)


urls = ("/start", "Start",
        "/stop", "Stop",
        "/chat", "Chat")

application = web.application(urls, globals()).wsgifunc()

app = web.application(urls, globals())
if __name__ == "__main__":
    app.run()
