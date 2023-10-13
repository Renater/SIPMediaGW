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

cspName = "outscale"
configFile = "config_sample.json"

thresholdTimeLine = {'00:00:00': {'capaMin':1, 'loadMax':0.90}, 
                     '09:00:00': {'capaMin':4, 'loadMax':0.75},
                     '12:00:00': {'capaMin':2, 'loadMax':0.80},
                     '14:00:00': {'capaMin':4, 'loadMax':0.75},
                     '17:00:00': {'capaMin':1, 'loadMax':0.90}}

# Get a manageInstance object from CSP file name
sys.path.append(cspName)
modName = cspName
print("CSP mod name: "+modName, flush=True)
mod = importlib.import_module(modName)
isClassMember = lambda member: inspect.isclass(member) and member.__module__ == modName
cspObj = inspect.getmembers(mod, isClassMember)[0][1]

csp = cspObj()
csp.configureInstance("{}/{}".format(cspName, configFile))

kamctlrc = dict()
kamctlrc['DBHOST'] = os.getenv('MYSQL_HOST')
kamctlrc['DBROOTPW'] = os.getenv('MYSQL_ROOT_PASSWORD')
cpuPerGW = os.getenv('CPU_PER_GW')

gwNamePart = os.environ.get('GW_NAME_PREFIX').replace('"',"").replace("'", "")

def getSeconds(stringHMS):
   timedeltaObj = dt.datetime.strptime(stringHMS, "%H:%M:%S") - dt.datetime(1900,1,1)
   return timedeltaObj.total_seconds()

def upScale(csp, numCPU):
    # cpuRange values must be multiples of 4
    cpuRange = list(csp.instType.keys())
    cpuRange.sort(reverse=True)
    for cpu in cpuRange:
        instNum = numCPU//int(cpu)
        numCPU = numCPU%int(cpu)
        for i in range(instNum):
            csp.createInstance(cpu, gwNamePart)
    if numCPU != 0:
        csp.createInstance(cpu, gwNamePart)

def downScale(csp, numGW):
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
        with closing(mysqlcon.connect(host=kamctlrc['DBHOST'],
                                      database='kamailio',
                                      user='root',
                                      password=kamctlrc['DBROOTPW'])) as con:
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
                                  ORDER BY count DESC;''',(gwNamePart,))
                vmList = cursor.fetchall()

                ipList = []
                for vm in vmList:
                    if vm['count'] <= numGW:
                        cursor.execute('''UPDATE location SET locked = 1
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

def scale(csp):
    currTime = dt.datetime.now().strftime("%H:%M:%S")
    th = min([ i for i in list(thresholdTimeLine.keys()) if i < currTime],
             key=lambda x:abs(getSeconds(x)-getSeconds(currTime)))

    try:
        with closing(mysqlcon.connect(host=kamctlrc['DBHOST'],
                                      database='kamailio',
                                      user='root',
                                      password=kamctlrc['DBROOTPW'])) as con:
            with closing(con.cursor()) as cursor:
                cursor.execute('''SELECT contact, username FROM location
                                WHERE
                                    username LIKE CONCAT('%',%s,'%')
                                    ;''',(gwNamePart,))
                contactList = cursor.fetchall()
                currentCapacity = len(contactList)

                cursor.execute('''SELECT callee_contact FROM dialog
                                WHERE
                                    callee_contact LIKE CONCAT('%',%s,'%')
                                    ;''',(gwNamePart,))
                contactList = cursor.fetchall()
                inCallNum = len(contactList)

                if currentCapacity < thresholdTimeLine[th]['capaMin']:
                    upScale(csp, (thresholdTimeLine[th]['capaMin'] - currentCapacity)*cpuPerGW)
                    currentCapacity = thresholdTimeLine[th]['capaMin']

                targetCapacity = max(thresholdTimeLine[th]['capaMin'], inCallNum/thresholdTimeLine[th]['loadMax'])
                capacityIncrease = math.ceil(targetCapacity - currentCapacity)
                if capacityIncrease > 0:
                    # Upscale
                    upScale(csp, capacityIncrease*cpuPerGW)
                if capacityIncrease < 0:
                    # Downscale
                    downScale(csp, abs(capacityIncrease))
            
    except mysqlcon.Error as err:
        print("Mysql error: {}".format(err), flush=True)