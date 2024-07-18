#!/usr/bin/env python
import math
import datetime as dt
import dateutil.parser as du
import json
from contextlib import closing
import mysql.connector as mysqlcon

def getSeconds(stringHMS):
   timedeltaObj = dt.datetime.strptime(stringHMS, "%H:%M:%S") - dt.datetime(1900,1,1)
   return timedeltaObj.total_seconds()

class Scaler:
    def __init__(self, cspObj):
        self.csp = cspObj

    def configure(self, configFile):
        f = open(configFile)
        self.config = json.load(f)
        f.close()

    def upScale(self, numCPU):
        # cpuRange values must be multiples of 4
        cpuRange = list(self.csp.instType.keys())
        cpuRange.sort(reverse=True)
        for cpu in cpuRange:
            instNum = numCPU//int(cpu)
            numCPU = numCPU%int(cpu)
            for i in range(instNum):
                self.csp.createInstance(cpu, self.config['gw_name_prefix'])
        if numCPU != 0:
            self.csp.createInstance(cpu, self.config['gw_name_prefix'])

    def downScale(self, numGW):
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
            with closing(mysqlcon.connect(host=self.config['sip_db']['host'],
                                        database='kamailio',
                                        user='root',
                                        password=self.config['sip_db']['root_password'])) as con:
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
                                    ORDER BY count DESC;''',(self.config['gw_name_prefix'],))
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
            self.csp.destroyInstances(ipList)

    def cleanup(self):
        try:
            with closing(mysqlcon.connect(host=self.config['sip_db']['host'],
                                        database='kamailio',
                                        user='root',
                                        password=self.config['sip_db']['root_password'])) as con:
                with closing(con.cursor(dictionary=True)) as cursor:
                    cursor.execute('''SELECT SUBSTRING_INDEX(SUBSTRING_INDEX(received,'sip:',-1),':',1) AS vm
                                    FROM location
                                    WHERE
                                        username LIKE CONCAT('%',%s,'%') AND to_stop = 1
                                    GROUP BY vm;''',(self.config['gw_name_prefix'],))
                    vmList = cursor.fetchall()
        except mysqlcon.Error as err:
            print("Mysql error: {}".format(err), flush=True)
            return

        ipList = []
        for vm in vmList:
            ipList.append(vm['vm'])
        if ipList:
            self.csp.destroyInstances(ipList)

        instList = self.csp.enumerateInstances()
        runningCpuCount = 0
        for inst in instList:
            runningCpuCount+= inst['cpu_count']
            if not inst['addr']['pub']:
                now = dt.datetime.now(dt.timezone.utc)
                start = du.parse(inst['start'])
                if (now-start).total_seconds() > 600:
                    self.csp.destroyInstances([inst['addr']['priv']])
        print('Number of running CPUs: {} \n'.format(runningCpuCount), flush=True)

    def scale(self, scaleTime=None, incallsNum=None):
        thresholdTimeLine = self.config['auto_scale_threshold']
        if not scaleTime:
            scaleTime = dt.datetime.now().strftime("%H:%M:%S")
        th = min([ i for i in list(thresholdTimeLine.keys()) if i <= scaleTime],
                key=lambda x:abs(getSeconds(x)-getSeconds(scaleTime)))

        try:
            with closing(mysqlcon.connect(host=self.config['sip_db']['host'],
                                        database='kamailio',
                                        user='root',
                                        password=self.config['sip_db']['root_password'])) as con:
                with closing(con.cursor()) as cursor:
                    cursor.execute('''SELECT contact, username FROM location
                                    WHERE
                                        username LIKE CONCAT('%',%s,'%') AND
                                        to_stop = 0
                                        ;''',(self.config['gw_name_prefix'],))
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
                                    );''',(self.config['gw_name_prefix'],))
                    contactList = cursor.fetchall()
                    readyToCallNum = len(contactList)

                    inCallNum = incallsNum if incallsNum else (currentCapacity - readyToCallNum )
                    minCapacity = thresholdTimeLine[th]['unlockedMin'] + inCallNum
                    if readyToCallNum < thresholdTimeLine[th]['unlockedMin']:
                        self.upScale(math.ceil(self.config['cpu_per_gw']*
                                                  (thresholdTimeLine[th]['unlockedMin'] - readyToCallNum)))
                        currentCapacity = thresholdTimeLine[th]['unlockedMin'] + inCallNum

                    targetCapacity = max(minCapacity, inCallNum/thresholdTimeLine[th]['loadMax'])
                    capacityIncrease = math.ceil(targetCapacity - currentCapacity)
                    if capacityIncrease > 0:
                        # Upscale
                        self.upScale(math.ceil(capacityIncrease*self.config['cpu_per_gw']))
                    if capacityIncrease < 0:
                        # Downscale
                        self.downScale(abs(capacityIncrease))
                    return 0
        except mysqlcon.Error as err:
            print("Mysql error: {}".format(err), flush=True)
