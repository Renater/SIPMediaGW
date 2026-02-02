#!/usr/bin/env python
import importlib
import sys
import time
import redis
from random import randint
import datetime as dt
import pandas as pd
import numpy as np
import math
import os
import json

import matplotlib.pyplot as plt

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')));
print(sys.path);

#from deploy.scaler.src.ScalerSIP import ScalerSIP
from deploy.scaler.src.ScalerMedia import ScalerMedia

from deploy.scaler.src.providers.fakescale.fakescale import Fakescale


def addGwToRedis(config, gwName, gwIp, gwType):
    startTime = dt.datetime.now().isoformat()
    statusUpdateTime = startTime
    gwValue = f"{gwIp}|started|{gwType}|{startTime}|{statusUpdateTime}"
    redisClient.set(f"gateway:{gwName}", gwValue)

def cleanRedis():
    for key in redisClient.scan_iter(match="gateway:*"):
        redisClient.delete(key)
    for key in redisClient.scan_iter(match="room:*"):
        redisClient.delete(key)

# Get an available gateway in Redis and lock it if it is found
def lockGw (config):
    for key in redisClient.scan_iter(match="gateway:*"):
        value = redisClient.get(key)
        parts = value.split("|")
        gwIp = parts[0]
        state = parts[1] if len(parts) > 1 else None
        if state == "started":
           redisClient.set(key, f"{gwIp}|working|{parts[2]}|{parts[3]}|{dt.datetime.now().isoformat()}")
           return {'username': key, 'ip': gwIp}
    return False

# free the gateway in Redis 
def unlockGw(config, username):
    value = redisClient.get(username)
    if value:
        parts = value.split("|")
        gwIp = parts[0]
        state = parts[1] if len(parts) > 1 else None
        if state == "working":
            redisClient.set(username, f"{gwIp}|started|{parts[2]}|{parts[3]}|{dt.datetime.now().isoformat()}")
        return True
    return False

def printGwStates():
    nbGWFree = 0
    nbGWWorking = 0
    nbGWStarting = 0
    nbGWStopping = 0
    nbGWStopped = 0
    keys = 0
    for key in redisClient.scan_iter(match="gateway:*"):
        value = redisClient.get(key)
        parts = value.split("|")
        state = parts[1] if len(parts) > 1 else None
        if state == "started":
            nbGWFree += 1
        elif state == "working":
            nbGWWorking += 1
        elif state == "starting":
            nbGWStarting += 1
        elif state == "stopping":
            nbGWStopping += 1
        elif state == "stopped":
            nbGWStopped += 1
        keys += 1
    print(f"Gateway states: Free: {nbGWFree}, Working: {nbGWWorking}, Starting: {nbGWStarting}, Stopping: {nbGWStopping}, Stopped: {nbGWStopped}, redis keys: {keys}", flush=True)


class Simuscale(Fakescale):
    def __init__(self, configFile, registerDelay):
        super().__init__()
        f = open(configFile)
        self.config = json.load(f)
        f.close()
        self.instToCreateList=[]
        self.simuTime = ''
        self.gwRegisterDelay = registerDelay
        self.gwCnt = 0
        self.cpuCnt = 0

    def createInstance(self, numCPU, gigaRAM, name=None, ip=None):
        ippAddr = super().createInstance(numCPU)
        numGw = int(int(numCPU)/self.config['cpu_per_gw'])
        if self.simuTime:
            for id in range(numGw):
                gwName = "{}.{}.{}".format(ippAddr, self.config['gw_name_prefix'], id)
                recv = "sip:{}:12345;transport=tcp".format(ippAddr)
                registerTime = self.simuTime + pd.Timedelta('{} seconds'.format(self.gwRegisterDelay
                                                                                + randint(0,60)))
                self.instToCreateList.append([gwName, recv, registerTime])
            self.cpuCnt += int(numCPU)
            self.instToCreateList = sorted(self.instToCreateList, key=lambda x: x[2])
            #print(f"Warning: scheduled {len(self.instToCreateList)} gateways for instance {ippAddr} ", flush=True)

    def destroyInstances(self, ipList):
        numDestroyedGws = 0
        for ip in ipList:
            for key in redisClient.scan_iter(match="gateway:*"):
                value = redisClient.get(key)
                parts = value.split("|")
                gwIp = parts[0]
                if gwIp == ip:
                    redisClient.delete(key)
                    numDestroyedGws += 1
        self.gwCnt -= numDestroyedGws
        self.cpuCnt -= numDestroyedGws * self.config['cpu_per_gw']
        #print(f"Warning: destroyed {numDestroyedGws} gateways for {len(ipList)} IPs", flush=True)

vcpuCostPerHour = 0.216/4
simuFreq = 60 # in seconds

scalerConfigFile = "deploy/scaler/config/scaler.json"
csp = Simuscale(scalerConfigFile, 60)
csp.configureInstance("deploy/scaler/src/providers/fakescale/config/sipmediagw_sample.json")
scaler = ScalerMedia(csp)
scaler.configure(scalerConfigFile)

redisClient = redis.Redis(host="127.0.0.1", port=6379, decode_responses=True)
result = redisClient.ping()
print(f"Redis connection status: {result}")

cleanRedis()

with open('test/scaler/simulations/17112020.csv', "r") as csvfile:
    callsList = pd.read_csv(csvfile, header=None,  parse_dates=[0, 1])

callsList.drop(callsList[callsList[1]-callsList[0] < pd.Timedelta('1 minutes')].index,
               inplace = True)

callsList = callsList.to_numpy().tolist()
callsList = sorted(callsList, key=lambda x: x[0])


firstCallStart = callsList[0][0].floor('D')

timeLine = pd.date_range(start=firstCallStart + pd.Timedelta('0 hours'),
                         end=firstCallStart + pd.Timedelta('24 hours'),
                         inclusive="left", freq='{}s'.format(simuFreq))

callsCount = []
gwsCount = []
rejectedCount = []
missedCount = []
vcpuCostCumul = []

incalls= []

callsByTry=[callsList, [], []]
maxTryNum = len(callsByTry)
csp.gwCnt = 0
csp.cpuCnt = 0
rejectCnt = 0
missedCnt = 0
currReject = 0
vcpuCost = 0

for timeId, currTime in enumerate(timeLine):
    csp.simuTime = currTime
    print (f"Simulation time: {currTime}, "
           f"Current incalls: {len(incalls)}, "
           f"Total rejected calls: {rejectCnt}, "
           f"Total missed calls: {missedCnt}, "
           f"Current gateways: {csp.gwCnt}, "
           f"Current vCPU: {csp.cpuCnt}", flush=True)

    ### Scaler
    if currTime.second == 0:
        scaler.scale(scaleTime=currTime.strftime("%H:%M:%S"))
    #print(f"New instance to create {len(csp.instToCreateList)}", flush=True)
    #printGwStates()

    ### Instances
    if csp.instToCreateList:
        while csp.instToCreateList[0][2] <= currTime:
            gw = csp.instToCreateList.pop(0)
            csp.gwCnt += 1
            addGwToRedis(scaler.config, gw[0], gw[1].split(':')[1], 'media')
            if not csp.instToCreateList:
                break
    ### Calls
    # To start
    for tryId in range(len(callsByTry)):
        calls = callsByTry[tryId]
        if calls:
            currConfStart = calls[0][0]
            tryLock = True
            while currConfStart <= currTime:
                gw = lockGw(scaler.config) if tryLock else False
                if gw:
                    newCall = calls.pop(0)
                    newCall.append(gw['username'])
                    incalls.append(newCall)
                else:
                    tryLock = False
                    if tryId >= maxTryNum - 1:
                        calls.pop(0)
                        missedCnt += 1
                    else:
                        retryConfStart = currTime + dt.timedelta(seconds=60)
                        calls[0][0] = retryConfStart
                        callsByTry[tryId+1].append(calls.pop(0))
                        rejectCnt += 1
                if not calls:
                    break
                currConfStart = calls[0][0]
    # To stop
    if incalls:
        incalls = sorted(incalls, key=lambda x: x[1])
        currConfStop = incalls[0][1]
        while currConfStop <= currTime:
            unlockGw(scaler.config, incalls[0][2])
            incalls.pop(0)
            if not incalls:
                break
            currConfStop = incalls[0][1]

    gwsCount.append(csp.gwCnt)
    callsCount.append(len(incalls))
    rejectedCount.append(rejectCnt)
    missedCount.append(missedCnt)

    currReject = 0
    for rej in callsByTry[1::]:
        currReject  += len(rej)

    cost = simuFreq*(csp.cpuCnt*vcpuCostPerHour/3600)
    vcpuCost += cost
    vcpuCostCumul.append(vcpuCost)

print("Start plotting")

fig, ax = plt.subplots(nrows=2, ncols=1)
x= (timeLine.astype(str).str[11:19]).values

step = math.ceil(len(x)/1000)

yCalls=np.array(callsCount)
ax[0].plot(x[::step], yCalls[::step], linewidth=2.0,
        label = f'Incalls number')

yGws=np.array(gwsCount)
ax[0].plot(x[::step], yGws[::step], linewidth=2.0,
        label = f'GWs number')

yReject=np.array(rejectedCount)
ax[0].plot(x[::step], yReject[::step], linewidth=2.0,
        label = f'Rejected calls count')

yMissed=np.array(missedCount)
ax[0].plot(x[::step], yMissed[::step], linewidth=2.0,
        label = f'Missed calls count')

yCost=np.array(vcpuCostCumul)
ax[1].plot(x[::step], yCost[::step], linewidth=2.0,
        label = f'VCPU cumulated cost')

for a in ax:
    a.legend(loc='upper left')
    a.xaxis.set_ticks(x[::step*int(len(x[::step])/6)])

# display the plot
plt.show()
# save the plot
fig.savefig("scaler_simulation.png")


print("end")