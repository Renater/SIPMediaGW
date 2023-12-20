#!/usr/bin/env python
import importlib
import sys
import datetime as dt
import inspect
from Scaler import Scaler

# Get a manageInstance object from CSP file name
cspName = "outscale"
cspConfigFile = "config/sipmediagw_staging.json"
sys.path.append(cspName)
modName = cspName
print("CSP mod name: "+modName, flush=True)
mod = importlib.import_module(modName)
isClassMember = lambda member: inspect.isclass(member) and member.__module__ == modName
cspObj = inspect.getmembers(mod, isClassMember)[0][1]

csp = cspObj('visio-dev')
csp.configureInstance("{}/{}".format(cspName, cspConfigFile))
scaler = Scaler(csp)

#while True:
try:
    scaler.configure("config/scaler.json")
    scaler.cleanup()
    scaler.scale()
except Exception as error:
    print("The scaler iteration failed:", error)
#time.sleep(60)
