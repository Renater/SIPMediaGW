#!/usr/bin/env python
import importlib
import sys
import os
import time
import traceback
import datetime as dt
import inspect
from Scaler import Scaler

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
scaler = Scaler(csp)

while True:
    try:
        scaler.configure("config/{}".
                         format(os.environ.get("SCALER_CONFIG_FILE")))
        scaler.cleanup()
        scaler.scale()
    except Exception as error:
        print("The scaler iteration failed:", error)
        traceback.print_exc(file=sys.stdout)
    time.sleep(60)
