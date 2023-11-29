#!/usr/bin/env python
import importlib
import sys
import time
import math
import datetime as dt
import os
import inspect
from contextlib import closing
import mysql.connector as mysqlcon

def getSeconds(stringHMS):
   timedeltaObj = dt.datetime.strptime(stringHMS, "%H:%M:%S") - dt.datetime(1900,1,1)
   return timedeltaObj.total_seconds()

def upScale(csp, params, numCPU):
    # cpuRange values must be multiples of 4
    cpuRange = list(csp.instType.keys())
    cpuRange.sort(reverse=True)
    for cpu in cpuRange:
        instNum = numCPU//int(cpu)
        numCPU = numCPU%int(cpu)
        for i in range(instNum):
            csp.createInstance(cpu, params['gwNamePart'])
    if numCPU != 0:
        csp.createInstance(cpu, params['gwNamePart'])

def downScale(csp, params, numGW):
    SQLCheck='''SELECT id
                    FROM location AS loc2
                    WHERE loc1.vm =
                        SUBSTRING_INDEX(SUBSTRING_INDEX(loc2.received,'sip:',-1),':',1) AND
                        loc2.locked = 1'''
    SQLCheckBis='''SELECT  callee_contact
                    FROM dialog
                    WHERE loc1.vm =
                        SUBSTRING_INDEX(SUBSTRING_INDEX(callee_contact,'alias=',-1),'~',1)'''
    try:
        with closing(mysqlcon.connect(host=params['DBHOST'],
                                      database='kamailio',
                                      user='root',
                                      password=params['DBROOTPW'])) as con:
            with closing(con.cursor(dictionary=True)) as cursor:
                cursor.execute('''SELECT vm, COUNT(username) as count
                                  FROM
                                      (SELECT *,
                                           SUBSTRING_INDEX(SUBSTRING_INDEX(received,'sip:',-1),':',1) AS vm
                                               FROM location) AS loc1
                                  WHERE
                                      loc1.locked = 0 AND
                                      loc1.username LIKE CONCAT('%',%s,'%') AND
                                      NOT EXISTS ('''+SQLCheck+''') AND
                                      NOT EXISTS ('''+SQLCheckBis+''')
                                  GROUP BY vm
                                  ORDER BY count DESC;''',(params['gwNamePart'],))
                vmList = cursor.fetchall()

                ipList = []
                for vm in vmList:
                    if vm['count'] <= numGW:
                        cursor.execute('''UPDATE location SET locked = 1, to_stop = 1
                                          WHERE
                                              locked = 0 AND
                                              SUBSTRING_INDEX(SUBSTRING_INDEX(location.received,'sip:',-1),':',1)=%s''',
                                        (vm['vm'],))
                        if cursor.rowcount == vm['count']:
                            con.commit()
                            ipList.append(vm['vm'])
                            numGW -= vm['count']
                        else:
                            con.rollback()

    except mysqlcon.Error as err:
        print("Mysql error: {}".format(err), flush=True)

    if ipList:
        csp.destroyInstances(ipList)

def cleanup(csp, params):
    try:
        with closing(mysqlcon.connect(host=params['DBHOST'],
                                      database='kamailio',
                                      user='root',
                                      password=params['DBROOTPW'])) as con:
            with closing(con.cursor(dictionary=True)) as cursor:
                cursor.execute('''SELECT SUBSTRING_INDEX(SUBSTRING_INDEX(received,'sip:',-1),':',1) AS vm
                                  FROM location
                                  WHERE
                                      username LIKE CONCAT('%',%s,'%') AND to_stop = 1
                                  GROUP BY vm;''',(params['gwNamePart'],))
                vmList = cursor.fetchall()
    except mysqlcon.Error as err:
        print("Mysql error: {}".format(err), flush=True)
        return

    ipList = []
    for vm in vmList:
        ipList.append(vm['vm'])
    if ipList:
        csp.destroyInstances(ipList)

def scale(csp, params, thresholdTimeLine, scaleTime=None, incallsNum=None):
    if not scaleTime:
        scaleTime = dt.datetime.now().strftime("%H:%M:%S")
    th = min([ i for i in list(thresholdTimeLine.keys()) if i <= scaleTime],
             key=lambda x:abs(getSeconds(x)-getSeconds(scaleTime)))

    try:
        with closing(mysqlcon.connect(host=params['DBHOST'],
                                      database='kamailio',
                                      user='root',
                                      password=params['DBROOTPW'])) as con:
            with closing(con.cursor()) as cursor:
                cursor.execute('''SELECT contact, username FROM location
                                WHERE
                                    username LIKE CONCAT('%',%s,'%') AND
                                    to_stop = 0
                                    ;''',(params['gwNamePart'],))
                contactList = cursor.fetchall()
                currentCapacity = len(contactList)

                cursor.execute('''SELECT contact, username FROM location
                                WHERE
                                    locked = 0 AND
                                    username LIKE CONCAT('%',%s,'%') AND
                                NOT EXISTS (
                                    SELECT callee_contact
                                    FROM dialog
                                    WHERE callee_contact LIKE CONCAT('%',location.username,'%')
                                );''',(params['gwNamePart'],))
                contactList = cursor.fetchall()
                readyToCallNum = len(contactList)

                inCallNum = incallsNum if incallsNum else (currentCapacity - readyToCallNum )
                minCapacity = thresholdTimeLine[th]['unlockedMin'] + inCallNum
                if readyToCallNum < thresholdTimeLine[th]['unlockedMin']:
                    upScale(csp, params, (thresholdTimeLine[th]['unlockedMin'] - readyToCallNum)*params['cpuPerGW'])
                    currentCapacity = thresholdTimeLine[th]['unlockedMin'] + inCallNum

                targetCapacity = max(minCapacity, inCallNum/thresholdTimeLine[th]['loadMax'])
                capacityIncrease = math.ceil(targetCapacity - currentCapacity)
                if capacityIncrease > 0:
                    # Upscale
                    upScale(csp, params, capacityIncrease*params['cpuPerGW'])
                if capacityIncrease < 0:
                    # Downscale
                    downScale(csp, params, abs(capacityIncrease))
            
    except mysqlcon.Error as err:
        print("Mysql error: {}".format(err), flush=True)
