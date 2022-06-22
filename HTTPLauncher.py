#!/usr/bin/python

import web
import json
import subprocess
import os
import docker

class Launcher:
    def GET(self, args=None):
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
        filePath = os.path.dirname(__file__)
        print(gwSubProc)
        res = subprocess.Popen(gwSubProc, cwd=filePath, stdout=subprocess.PIPE)
        res.wait()
        resStr = res.stdout.read().decode('utf-8')
        resJson = json.loads(resStr.replace("'", '"'))

        return json.dumps(resJson)

class Status:
    def GET(self, args=None):
        client = docker.from_env()

        callsEnded = True
        readyToCall = 0
        for i in range(8):
            try:
                gateway = client.containers.get(f"gw{i}")

                if gateway.status == "running":
                    callsEnded = False

                readyToCall += "chrome" not in str(gateway.exec_run("ps -e").output)

            except:
                break

        return {"readyToCall": readyToCall, "callsEnded": callsEnded}

urls = "/(.*)", "Launcher"
application = web.application(urls, globals()).wsgifunc()

urls = ("/sipmediagw", "Launcher",
    "/status", "Status")

app = web.application(urls, globals())
if __name__ == "__main__":
    app.run()
