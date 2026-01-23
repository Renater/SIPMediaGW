#!/usr/bin/env python
import importlib
import sys
import os
import datetime as dt
import inspect
import re
import web
import json
from deploy.scaler.src.ScalerSIP  import ScalerSIP
from deploy.scaler.src.ScalerMedia import ScalerMedia

scalerConfigFile = os.environ.get("SCALER_CONFIG_FILE", "scaler.json")
cspName =  os.environ.get("CSP_NAME", "outscale")
cspConfigFile = os.environ.get("CSP_CONFIG_FILE", "sipmediagw_sample.json")
cspProfile = os.environ.get("CSP_PROFILE", "visio-dev")

scalerType = os.environ.get("SCALER_TYPE", "SIP")

def authorize(func):
    def inner(*args, **kwargs):
        try:
            token = args[0].scaler.config['api_token']
        except:
            return json.dumps({'Error': 'internal error'})
        auth = web.ctx.env.get('HTTP_AUTHORIZATION')
        authReq = False
        if auth is None:
            authReq = True
        else:
            auth = re.sub('^Bearer ', '', auth)
            if auth != token:
                authReq = True
        if not authReq:
            return func(*args, **kwargs)
        else:
            web.header('WWW-Authenticate', 'Bearer error="invalid_token"')
            web.ctx.status = '401 Unauthorized'
            return json.dumps({'Error': 'authorization error'})
    return inner

class Scaling:
    def __init__(self) -> None:
        # Get a manageInstance object from CSP file name

        sys.path.append(cspName)
        modName = cspName
        print("CSP mod name: "+modName, flush=True)
        mod = importlib.import_module(modName)
        isClassMember = lambda member: inspect.isclass(member) and member.__module__ == modName
        cspObj = inspect.getmembers(mod, isClassMember)[0][1]

        csp = cspObj(cspProfile)
        #initData = {}
        #csp.configureInstance("{}/config/{}".format(cspName, cspConfigFile), initData)
        
        if scalerType.upper() == "SIP":
            self.scaler = ScalerSIP(csp)
        else:
            self.scaler = ScalerMedia(csp)

        self.scaler.configure("config/{}".format(scalerConfigFile))

    @authorize
    def GET(self, args=None):
        data = web.input()
        if 'auto' in data.keys():
            initData = { 'callin' : {}}
            self.scaler.csp.configureInstance("{}/config/{}".format(cspName, cspConfigFile), initData)
            try:
                self.scaler.cleanup()
                if self.scaler.scale() == 0:
                    web.ctx.status = '200 OK'
                    return json.dumps({"status": "success", "message": "The scaler iteration succeed"})
            except Exception as error:
                return "The scaler iteration failed: {}".format(error)
        if 'up' in data.keys():
            roomId = '0'
            initData = {}
            if 'roomId' in data.keys():
                roomId = data['roomId']
                if 'dialOut' in data.keys():
                    initData['callout'] = {'dial' : data['dialOut'], 'room' : roomId}
                if 'rtmpUri' in data.keys():
                    initData['streaming'] = {'rtmp' : data['rtmpUri'], 'room' : roomId}
                if 'apiKey' in data.keys() and 'userMail' in data.keys():
                    initData['recording'] = {'key' : data['apiKey'],
                                             'mail' : data['userMail'], 'room' : roomId}

            # Ensure that the gateway will be in the "callin" pool (waiting an incoming  call) at the end...
            initData ['callin'] = {}
            self.scaler.csp.configureInstance("{}/config/{}".format(cspName, cspConfigFile), initData)
            try:
                instRes = self.scaler.csp.createInstance('4', name='mediagw')
                web.ctx.status = '200 OK'
                return json.dumps({"status": "success", "instance": instRes})
            except Exception as error:
                web.ctx.status = '500 Internal Server Error'
                return json.dumps({"Error": "Instance creation failed: {}".format(error)})



urls = ("/scale", "Scaling")

app = web.application(urls, globals())

if __name__ == "__main__":
    app.run()
