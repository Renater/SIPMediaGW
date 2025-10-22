#!/usr/bin/python3

import web
import json
import re
import subprocess
import os

allowedToken = '1234'

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
            gwSubProc.extend(['-k', data['apiKey']])
        if 'recipientMail' in data:
            gwSubProc.extend(['-m', data['recipientMail']])

        filePath = os.path.dirname(__file__)
        print(gwSubProc)
        res = subprocess.Popen(gwSubProc, cwd=filePath, stdout=subprocess.PIPE)
        res.wait()
        resStr = res.stdout.read().decode('utf-8')
        resJson = json.loads(resStr.replace("'", '"'))

        web.ctx.status = '200 OK'
        return json.dumps({"status": "success", "details": resJson})

class Progress:
    @authorize
    def GET(self, args=None):
        data = web.input()
        web.header('Content-Type', 'application/json')
        #ipdb.set_trace()
        if 'room' in data.keys() and data['room'] != '0':
            projectName = sanitize_for_compose_project_name(data['room'])
            try:
                gwSubProc = ['docker', 'compose', '-p', projectName, 'ps', '--format', 'json']
                res = subprocess.Popen(gwSubProc, cwd='.', stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                out, err = res.communicate()
                decoded = out.decode('utf-8').strip()
                try:
                    parsed = json.loads(decoded)
                    if isinstance(parsed, dict):
                        result = [parsed]
                    elif isinstance(parsed, list):
                        result = parsed
                    else:
                        raise ValueError("Unexpected format")
                except json.JSONDecodeError:
                    result = [json.loads(line) for line in decoded.split('\n') if line.strip()]
                resp = {"status": "success"}
                web.ctx.status = '200 OK'
                if not result:
                    resp['gw_state'] = "down"
                    return json.dumps(resp)

                gwData = next((c for c in result if c.get("Name", "").startswith("gw")), None)
                gwName = gwData['Name']
                # Recording progress
                gwSubProc = ['docker', 'exec', gwName,
                             'sh', '-c',
                             ('[ "$MAIN_APP" = "recording" ] && '
                              'pid=$(pgrep -o ffmpeg) && '
                              '[ -n "$pid" ] && '
                              'ps -p $pid -o etimes= | '
                              'awk \'{ sec=$1; h=int(sec/3600); m=int((sec%3600)/60); s=sec%60; '
                              'printf "%02d:%02d:%02d", h, m, s }\'')]
                res = subprocess.Popen(gwSubProc, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                out, err = res.communicate()
                recordElapsed = out.decode()
                if recordElapsed:
                    resp["recording_duration"] = recordElapsed
                gwSubProc = ['docker', 'exec', gwName, 'sh', '-c', 'echo $WITH_TRANSCRIPT']
                res = subprocess.Popen(gwSubProc, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                out, err = res.communicate()
                withTranscript = out.decode()
                if withTranscript == 'true':
                    # Transcript progress
                    gwSubProc = ['docker', 'exec', gwName, 'sh', '-c', 'ls /var/recording/*.mp4']
                    res = subprocess.Popen(gwSubProc, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    out, err = res.communicate()
                    mp4List = out.decode().split()
                    processedPercent = (
                        f"{(sum(f.endswith('.processed.mp4') for f in mp4List) / len(mp4List) * 100):.0f}%"
                        if mp4List else "0%"
                    )
                    resp["transcript_progress"] = processedPercent
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
        resJson = {}
        web.header('Content-Type', 'application/json')
        if 'room' in data.keys() and data['room'] != '0':
            gwSubProc = ['docker', 'compose', 'ls','--format', 'json', '-q' ]
            res = subprocess.Popen(gwSubProc, cwd='.', stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            res.wait()
            resStr = res.stdout.read().decode('utf-8')
            projects=resStr.splitlines()
            projectName = sanitize_for_compose_project_name(data['room'])
            if projectName in projects:
                gwSubProc = ['docker', 'compose']
                gwSubProc.extend(['-p', projectName])
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
        "/progress", "Progress",
        "/chat", "Chat")

application = web.application(urls, globals()).wsgifunc()

app = web.application(urls, globals())
if __name__ == "__main__":
    app.run()
