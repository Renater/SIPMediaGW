#!/usr/bin/env python
import importlib
import sys
import os
import datetime as dt
import inspect
import web
from Scaler import Scaler


class Scaling:
    def __init__(self) -> None:
        # Get a manageInstance object from CSP file name
        cspName =  os.environ.get("CSP_NAME")
        cspConfigFile = "config/{}".format(os.environ.get("CSP_CONFIG_FILE"))
        sys.path.append(cspName)
        modName = cspName
        print("CSP mod name: "+modName, flush=True)
        mod = importlib.import_module(modName)
        isClassMember = lambda member: inspect.isclass(member) and member.__module__ == modName
        cspObj = inspect.getmembers(mod, isClassMember)[0][1]

        csp = cspObj(os.environ.get("CSP_PROFILE"))
        csp.configureInstance("{}/{}".format(cspName, cspConfigFile))
        self.scaler = Scaler(csp)

    def GET(self, args=None):
        try:
            self.scaler.configure("config/{}".
                             format(os.environ.get("SCALER_CONFIG_FILE")))
            self.scaler.cleanup()
            if self.scaler.scale() == 0:
                return "The scaler iteration succeed"
        except Exception as error:
            return "The scaler iteration failed: {}".format(error)


urls = ("/scale", "Scaling")

app = web.application(urls, globals())

if __name__ == "__main__":
    app.run()