#!/usr/bin/env python
import importlib
import sys
import time
from random import randint
import datetime as dt
import pandas as pd
import numpy as np
import math
import os
import json
from contextlib import closing
import mysql.connector as mysqlcon

import matplotlib.pyplot as plt

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '../../../')));
print(sys.path);

from deploy.scaler.src.ScalerSIP import ScalerSIP
from deploy.scaler.src.providers.fakescale.fakescale import Fakescale

def kamDbInsert(config, gwName, recv):
    try:
        with closing(mysqlcon.connect(host=config['sip_db']['host'],
                                database='kamailio',
                                user='root',
                                password=config['sip_db']['root_password'])) as con:
            with closing(con.cursor()) as cursor:
                    cursor.execute('''INSERT INTO location (username, ruid, received) VALUES (%s, %s, %s);''',
                                   (gwName, gwName, recv,))
                    con.commit()
    except mysqlcon.Error as err:
            print("Mysql error: {}".format(err), flush=True)

def cleanLocationTable(config):
    with closing(mysqlcon.connect(host=config['sip_db']['host'],
                                  database='kamailio',
                                  user='root',
                                  password=config['sip_db']['root_password'])) as con:
        with closing(con.cursor(dictionary=True)) as cursor:
            cursor.execute('''TRUNCATE location''')
            con.commit()

def lockGw (config):
    res=''
    with closing(mysqlcon.connect(host=config['sip_db']['host'],
                                  database='kamailio',
                                  user='root',
                                  password=config['sip_db']['root_password'])) as con:
        with closing(con.cursor(dictionary=True)) as cursor:
            cursor.execute('''SELECT contact, username, socket,
                                        SUBSTRING_INDEX(SUBSTRING_INDEX(received,'sip:',-1),':',1) AS vm,
                                        COUNT(username) as count FROM location
                                WHERE
                                    locked = 0 AND
                                    username LIKE CONCAT('%',%s,'%') AND
                                    EXISTS (
                                        SELECT  callee_contact
                                        FROM dialog
                                        WHERE SUBSTRING_INDEX(SUBSTRING_INDEX(callee_contact,'alias=',-1),'~',1) =
                                            SUBSTRING_INDEX(SUBSTRING_INDEX(location.received,'sip:',-1),':',1)
                                    )
                                GROUP BY vm
                                ORDER BY count ASC;''',(config['gw_name_prefix'],))
            contactList = cursor.fetchall()
            if len(contactList) == 0:
                cursor.execute('''SELECT contact, username, socket,
                                        SUBSTRING_INDEX(SUBSTRING_INDEX(received,'sip:',-1),':',1) AS vm,
                                        COUNT(username) as count FROM location
                                WHERE
                                    locked = 0 AND
                                    username LIKE CONCAT('%',%s,'%') AND
                                    NOT EXISTS (
                                        SELECT  callee_contact
                                        FROM dialog
                                        WHERE SUBSTRING_INDEX(SUBSTRING_INDEX(callee_contact,'alias=',-1),'~',1) =
                                                SUBSTRING_INDEX(SUBSTRING_INDEX(location.received,'sip:',-1),':',1)
                                    )
                                GROUP BY vm
                                ORDER BY count ASC;''',(config['gw_name_prefix'],))
                contactList = cursor.fetchall()
                if len(contactList) == 0:
                    return False
            for contact in contactList:
                cursor.execute('''UPDATE location SET locked = 1
                                    WHERE
                                        location.username = %s AND
                                        locked = 0 AND
                                        NOT EXISTS (
                                            SELECT callee_contact
                                            FROM dialog
                                            WHERE callee_contact LIKE CONCAT('%',%s,'%')
                                        );''',(contact['username'], contact['username'],))
                res = con.commit()
                if cursor.rowcount > 0:
                    return contact
    return False

def unlockGw(config, username):
    with closing(mysqlcon.connect(host=config['sip_db']['host'],
                                  database='kamailio',
                                  user='root',
                                  password=config['sip_db']['root_password'])) as con:
        with closing(con.cursor()) as cursor:
            cursor.execute('''UPDATE location SET locked = 0
                              WHERE  username LIKE CONCAT('%',%s,'%');''',
                           (username,))
            res = con.commit()

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

    def createInstance(self, numCPU, name=None, ip=None):
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

    def destroyInstances(self, ipList):
          for ip in ipList:
            try:
                with closing(mysqlcon.connect(host=self.config['sip_db']['host'],
                                        database='kamailio',
                                        user='root',
                                        password=self.config['sip_db']['root_password'])) as con:
                    with closing(con.cursor()) as cursor:
                            cursor.execute('''DELETE FROM location 
                                                WHERE 
                                                    SUBSTRING_INDEX(SUBSTRING_INDEX(received,'sip:',-1),':',1) = %s
                                            ;''', (ip,))
                            con.commit()
                            self.gwCnt -= cursor.rowcount
                            self.cpuCnt -= (cursor.rowcount*self.config['cpu_per_gw'])
            except mysqlcon.Error as err:
                    print("Mysql error: {}".format(err), flush=True)
          super().destroyInstances(ipList)

vcpuCostPerHour = 0.216/4
simuFreq = 60 # in seconds

scalerConfigFile = "deploy/scaler/config/scaler.json"
csp = Simuscale(scalerConfigFile, 60)
csp.configureInstance("deploy/scaler/src/providers/fakescale/config/sipmediagw_sample.json")
scaler = ScalerSIP(csp)
scaler.configure(scalerConfigFile)

cleanLocationTable(scaler.config)

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
    ### Scaler
    if currTime.second == 0:
        scaler.scale(scaleTime=currTime.strftime("%H:%M:%S"))
    ### Instances
    if csp.instToCreateList:
        while csp.instToCreateList[0][2] <= currTime:
            gw = csp.instToCreateList.pop(0)
            kamDbInsert(scaler.config, gw[0], gw[1])
            csp.gwCnt += 1
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