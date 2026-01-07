
# HTTP Launcher Stub used to ffake test the HTTP Launcher Gateway

#!/usr/bin/python3

import web
import json
import re
import subprocess
import os
import redis
import datetime as dt

redisClient = redis.Redis(host='redis', port=6379, db=0, decode_responses=True)
allowedToken = '1234'
nbGw = 0

def sanitize_for_compose_project_name(name: str) -> str:
    # Lowercase everything
    name = name.lower()

    # Replace invalid characters with underscores
    name = re.sub(r'[^a-z0-9_-]+', '_', name)

    # Ensure it starts with a letter or digit
    if not re.match(r'^[a-z0-9]', name):
        name = 'p_' + name

    # Trim to max 63 characters
    name = name[:63]

    # Remove trailing non-alphanumeric characters (for cleanliness)
    name = re.sub(r'[^a-z0-9]+$', '', name)

    return name

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
    def GET(self, args=None):
        data = web.input()
        resJson = {}
        web.header('Content-Type', 'application/json')
        print(f"Request Data: {data}")
        if 'room' in data.keys() and data['room'] != '0' and 'gwName' in data.keys() and data['gwName'] != '0':
            # lock a gateway in the redis
            gwName = data['gwName']
            value = redisClient.get(gwName)
            parts = value.split("|")
            gwIp = parts[0]
            state = parts[1] if len(parts) > 1 else None
            if state == "started":
                redisClient.set(gwName, f"{gwIp}|working|{parts[2]}|{parts[3]}|{dt.datetime.now().isoformat()}")
                resJson = {"status": "success"}
                web.ctx.status = '200 OK'
            else:
                web.ctx.status = '404 Not Found'
                resJson = {"Error": "no available gateway found"}   
        else:
            web.ctx.status = '400 Bad Request'
        
        return json.dumps(resJson)

class Progress:
    @authorize
    def GET(self, args=None):
        data = web.input()
        web.header('Content-Type', 'application/json')
        if 'room' in data.keys() and data['room'] != '0':
            projectName = sanitize_for_compose_project_name(data['room'])
            try:
                resp = {"status": "success"}
                web.ctx.status = '200 OK'
                return json.dumps(resp)
            except:
                web.ctx.status = '404 Not Found'
                return json.dumps({"Error": "something wrong happened"})
        else:
            web.ctx.status = '400 Bad Request'
            return json.dumps({"Error": "a room name must be specified"})

class Stop:
    @authorize
    def GET(self, args=None):
        data = web.input()
        web.header('Content-Type', 'application/json')
        if 'gwName' in data.keys() and data['gwName'] != '0':
            try:
                resp = {"status": "success"}
                web.ctx.status = '200 OK'
                # Unlock by updating the gateway status in Redis
                gwName = data['gwName']
                value = redisClient.get(gwName)
                parts = value.split("|")
                gwIp = parts[0]
                redisClient.set(gwName, f"{gwIp}|started|{parts[2]}|{parts[3]}|{dt.datetime.now().isoformat()}")
                return json.dumps(resp)
            except:
                web.ctx.status = '404 Not Found'
                return json.dumps({"Error": "something wrong happened"})
        else:
            web.ctx.status = '400 Bad Request'
            return json.dumps({"Error": "a gwName must be specified"})

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

class AddGatewayVM:
    def GET(self, args=None):
        data = web.input()
        resJson = {}
        global nbGw
        web.header('Content-Type', 'application/json')
        if 'gwIp' in data.keys() and data['gwIp'] != '0':
            gwIp = data['gwIp']
            gwName = f"{gwIp}-gw{nbGw}"
            nbGw += 1
            gwType = data.get('gwType', 'media')
            startTime = dt.datetime.now().isoformat()
            statusUpdateTime = startTime
            gwValue = f"{gwIp}|started|{gwType}|{startTime}|{statusUpdateTime}"
            redisClient.set(f"gateway:{gwName}", gwValue)
            web.ctx.status = '200 OK'
            resJson = {'gwName': gwName, 'gwIp': gwIp, 'gwType': gwType}
        else:
            web.ctx.status = '400 Bad Request'
        
        return json.dumps({"status": "success", "details": resJson})

class RemoveGatewayVM:
    global nbGw
    def GET(self, args=None):
        data = web.input()
        resJson = {}
        global nbGw

        web.header('Content-Type', 'application/json')
        if 'gwName' in data.keys() and data['gwName'] != '0':
            gwName = data['gwName']
            redisClient.delete(f"gateway:{gwName}")
            web.ctx.status = '200 OK'
            nbGw -= 1
            resJson = {'gwName': gwName, 'removed': True}
        else:
            web.ctx.status = '400 Bad Request'
        
        return json.dumps({"status": "success", "details": resJson})

urls = ("/start", "Start",
        "/stop", "Stop",
        "/progress", "Progress",
        "/chat", "Chat",
        "/add_gateway_vm", "AddGatewayVM",
        "/remove_gateway_vm", "RemoveGatewayVM")

application = web.application(urls, globals()).wsgifunc()

app = web.application(urls, globals())
if __name__ == "__main__":
    app.run()
