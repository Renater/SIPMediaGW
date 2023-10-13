#!/usr/bin/env python
import importlib
import sys
import time
from random import randint
import datetime as dt
import os
import threading
from contextlib import closing
import mysql.connector as mysqlcon
import scaler

sys.path.append('fakescale')
from fakescale import Fakescale

configFile = "config_sample.json"

def kamDbInsert(params, ippAddr, numGw):
    gwRegisterDelay = 0
    time.sleep(gwRegisterDelay)
    for id in range(numGw):
        gwName = "{}.{}.{}".format(ippAddr, params['gwNamePart'], id)
        recv = "sip:{}:12345;transport=tcp".format(ippAddr)
        try:
            with closing(mysqlcon.connect(host=params['DBHOST'],
                                    database='kamailio',
                                    user='root',
                                    password=params['DBROOTPW'])) as con:
                with closing(con.cursor()) as cursor:
                        cursor.execute('''INSERT INTO location (username, ruid, received) VALUES (%s, %s, %s)
                                        ;''', (gwName, randint(0,9999), recv,))
                        con.commit()
        except mysqlcon.Error as err:
                print("Mysql error: {}".format(err), flush=True)

class Simuscale(Fakescale):
    def __init__(self, params):
        super().__init__()
        self.params = params

    def createInstance(self, numCPU, name=None, ip=None):
        ippAddr = super().createInstance(numCPU)
        numGw = int(int(numCPU)/params['cpuPerGW'])
        kamDbInsertThread = threading.Thread(target=kamDbInsert, args=(self.params, ippAddr, numGw,))
        kamDbInsertThread.start()
        print(ippAddr)

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
            except mysqlcon.Error as err:
                    print("Mysql error: {}".format(err), flush=True)
          super().destroyInstances(ipList)

thresholdTimeLine = {'00:00:00': {'capaMin':1, 'loadMax':0.90},
                     '09:00:00': {'capaMin':4, 'loadMax':0.75},
                     '12:00:00': {'capaMin':2, 'loadMax':0.80},
                     '14:00:00': {'capaMin':4, 'loadMax':0.75},
                     '17:00:00': {'capaMin':1, 'loadMax':0.90}}

params = dict()
params['DBHOST'] = '127.0.0.1'
params['DBROOTPW'] = 'dbrootpw'
params['cpuPerGW'] = 4

params['gwNamePart'] = 'mediagw'

csp = Simuscale(params)
csp.configureInstance("{}/{}".format("fakescale", configFile))

scaler.scale(csp, params, thresholdTimeLine)

