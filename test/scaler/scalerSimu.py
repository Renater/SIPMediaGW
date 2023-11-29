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
from contextlib import closing
import mysql.connector as mysqlcon
import scaler
import matplotlib.pyplot as plt

sys.path.append('fakescale')
from fakescale import Fakescale

configFile = "config_sample.json"

def kamDbInsert(params, gwName, recv):
    try:
        with closing(mysqlcon.connect(host=params['DBHOST'],
                                database='kamailio',
                                user='root',
                                password=params['DBROOTPW'])) as con:
            with closing(con.cursor()) as cursor:
                    cursor.execute('''INSERT INTO location (username, ruid, received) VALUES (%s, %s, %s);''',
                                   (gwName, gwName, recv,))
                    con.commit()
    except mysqlcon.Error as err:
            print("Mysql error: {}".format(err), flush=True)

def cleanLocationTable(params):
    with closing(mysqlcon.connect(host=params['DBHOST'],
                                  database='kamailio',
                                  user='root',
                                  password=params['DBROOTPW'])) as con:
        with closing(con.cursor(dictionary=True)) as cursor:
            cursor.execute('''TRUNCATE location''')
            con.commit()

def lockGw (params):
    res=''
    with closing(mysqlcon.connect(host=params['DBHOST'],
                                  database='kamailio',
                                  user='root',
                                  password=params['DBROOTPW'])) as con:
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
                                ORDER BY count ASC;''',(params['gwNamePart'],))
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
                                ORDER BY count ASC;''',(params['gwNamePart'],))
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

def unlockGw(params, username):
    with closing(mysqlcon.connect(host=params['DBHOST'],
                                  database='kamailio',
                                  user='root',
                                  password=params['DBROOTPW'])) as con:
        with closing(con.cursor()) as cursor:
            cursor.execute('''UPDATE location SET locked = 0
                              WHERE  username LIKE CONCAT('%',%s,'%');''',
                           (username,))
            res = con.commit()

class Simuscale(Fakescale):
    def __init__(self, params, registerDelay):
        super().__init__()
        self.params = params
        self.instToCreateList=[]
        self.simuTime = ''
        self.gwRegisterDelay = registerDelay
        self.gwCnt = 0
        self.cpuCnt = 0

    def createInstance(self, numCPU, name=None, ip=None):
        ippAddr = super().createInstance(numCPU)
        numGw = int(int(numCPU)/params['cpuPerGW'])
        if self.simuTime:
            for id in range(numGw):
                gwName = "{}.{}.{}".format(ippAddr, params['gwNamePart'], id)
                recv = "sip:{}:12345;transport=tcp".format(ippAddr)
                registerTime = self.simuTime + pd.Timedelta('{} seconds'.format(self.gwRegisterDelay
                                                                                + randint(0,60)))
                self.instToCreateList.append([gwName, recv, registerTime])
            self.cpuCnt += int(numCPU)
            self.instToCreateList = sorted(self.instToCreateList, key=lambda x: x[2])

    def destroyInstances(self, ipList):
          for ip in ipList:
            try:
                with closing(mysqlcon.connect(host=params['DBHOST'],
                                        database='kamailio',
                                        user='root',
                                        password=params['DBROOTPW'])) as con:
                    with closing(con.cursor()) as cursor:
                            cursor.execute('''DELETE FROM location 
                                                WHERE 
                                                    SUBSTRING_INDEX(SUBSTRING_INDEX(received,'sip:',-1),':',1) = %s
                                            ;''', (ip,))
                            con.commit()
                            self.gwCnt -= cursor.rowcount
                            self.cpuCnt -= (cursor.rowcount*params['cpuPerGW'])
            except mysqlcon.Error as err:
                    print("Mysql error: {}".format(err), flush=True)
          super().destroyInstances(ipList)

thresholdTimeLine = {'00:00:00': {'unlockedMin':2, 'loadMax':0.9},
                     '07:00:00': {'unlockedMin':4, 'loadMax':0.75},
                     '09:00:00': {'unlockedMin':8, 'loadMax':0.75},
                     '10:30:00': {'unlockedMin':8, 'loadMax':0.75},
                     '12:30:00': {'unlockedMin':4, 'loadMax':0.8},
                     '13:00:00': {'unlockedMin':8, 'loadMax':0.75},
                     '14:30:00': {'unlockedMin':4, 'loadMax':0.75},
                     '17:00:00': {'unlockedMin':2, 'loadMax':0.8},
                     '20:00:00': {'unlockedMin':2, 'loadMax':0.9}}

vcpuCostPerHour = 0.216/4

params = dict()
params['DBHOST'] = '127.0.0.1'
params['DBROOTPW'] = 'dbrootpw'
params['cpuPerGW'] = 4

params['gwNamePart'] = 'mediagw'

csp = Simuscale(params, 60)
csp.configureInstance("{}/{}".format("fakescale", configFile))
cleanLocationTable(params)

with open('17112020.csv', "r") as csvfile:
    callsList = pd.read_csv(csvfile, header=None,  parse_dates=[0, 1])

callsList.drop(callsList[callsList[1]-callsList[0] < pd.Timedelta('1 minutes')].index,
               inplace = True)

callsList = callsList.to_numpy().tolist()
callsList = sorted(callsList, key=lambda x: x[0])


firstCallStart = callsList[0][0].floor('D')

simuFreq = 1
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
    #callsCount.append(callsCount[timeId-1]) if timeId > 0 else callsCount.append(0)
    csp.simuTime = currTime
    ### Scaler
    if currTime.second == 0:
        scaler.scale(csp, params, thresholdTimeLine, currTime.strftime("%H:%M:%S"))
    ### Instances
    if csp.instToCreateList:
        while csp.instToCreateList[0][2] <= currTime:
            gw = csp.instToCreateList.pop(0)
            kamDbInsert(params, gw[0], gw[1])
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
                gw = lockGw(params) if tryLock else False
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
            unlockGw(params, incalls[0][2])
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

print("end")