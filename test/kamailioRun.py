#!/usr/bin/env python
import os
import subprocess
import sqlite3
from contextlib import closing

dbPath = '/usr/local/etc/kamailio/kamailio.sqlite'

def unlock(dstUser):
    with closing(sqlite3.connect(dbPath)) as con:
        with closing(con.cursor()) as cursor:
            cursor.execute('''UPDATE location SET locked = 0
                              WHERE  contact LIKE '%'||?||'%';''',
                           (dstUser,))
            res = con.commit()

with open(dbPath, 'a'):
    try:
        subprocess.run(['kamdbctl create'], shell=True)
        with closing(sqlite3.connect(dbPath)) as con:
            with closing(con.cursor()) as cursor:
                cursor.execute('''ALTER TABLE location
                                  ADD COLUMN locked INTEGER NOT NULL DEFAULT 0''')
                res = con.commit()
    except:
        pass

cmd = subprocess.Popen('kamailio -DD -E', stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)

while True:
    try:
        line = cmd.stdout.readline()
        if line:
            logs = line.decode()
            try:
                if logs.find('ACC: call missed:') != -1:
                    accLog = logs.split('ACC: call missed:')[1]
                    accDict = dict(el.split("=") for el in accLog.split(";"))
                    if accDict['code'] == '500':
                        print('Unlock gateway: ',accDict['dst_user'], '\n', flush=True)
                        unlock(accDict['dst_user'])
            except:
                print('ACC logs parsing error \n', flush=True)
            print(logs, end='', flush=True)
    except:
        pass


