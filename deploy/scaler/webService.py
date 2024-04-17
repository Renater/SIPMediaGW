#!/usr/bin/env python
import importlib
import sys
import os
import datetime as dt
import inspect
import re
import web
from Scaler import Scaler

scalerConfigFile = os.environ.get("SCALER_CONFIG_FILE", "scaler.json")
cspName =  os.environ.get("CSP_NAME", "outscale")
cspConfigFile = os.environ.get("CSP_CONFIG_FILE", "sipmediagw_sample.json")
cspProfile = os.environ.get("CSP_PROFILE", "visio-dev")

def authorize(func):
    def inner(*args, **kwargs):
        try:
            token = args[0].scaler.config['api_token']
        except:
            return 'internal error'
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
            return 'authorization error'
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
        self.scaler = Scaler(csp)
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
                    return "The scaler iteration succeed"
            except Exception as error:
                return "The scaler iteration failed: {}".format(error)
        if 'up' in data.keys():
            roomId = '0'
            if 'roomId' in data.keys():
                roomId= data['roomId']
            if 'dialOut' in data.keys():
                initData = {'callout' : { 'dial' : data['dialOut'], 'room' : roomId},
                            'callin' : {}}
                self.scaler.csp.configureInstance("{}/config/{}".format(cspName, cspConfigFile), initData)
                try:
                    return self.scaler.csp.createInstance('4', name='mediagw')
                except Exception as error:
                    return "Instance creation failed: {}".format(error)



urls = ("/scale", "Scaling")

app = web.application(urls, globals())

if __name__ == "__main__":
    app.run()