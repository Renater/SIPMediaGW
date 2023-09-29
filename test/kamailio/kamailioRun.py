#!/usr/bin/env python3
import os
import subprocess
from contextlib import closing
import mysql.connector as mysqlcon

db = {
  'host': os.environ.get('DBHOST'),
  'user': os.environ.get('DBRWUSER'),
  'pwd': os.environ.get('DBRWPW'),
  'root_pwd' : os.environ.get('DBROOTPW'),
  'name': os.environ.get('DBNAME')}

def unlock(dstUser):
    with closing(mysqlcon.connect(host=db['host'],
                                  user=db['user'],
                                  password=db['pwd'],
                                  database=db['name'])) as con:
        with closing(con.cursor()) as cursor:
            cursor.execute('''UPDATE location SET locked = 0
                              WHERE  contact LIKE CONCAT('%',%s,'%');''',
                           (dstUser,))
            res = con.commit()

try:
    with closing(mysqlcon.connect(host=db['host'],
                                  user='root',
                                  password=db['root_pwd'])) as con:
        with closing(con.cursor()) as cursor:
            cursor.execute('''SET PERSIST sql_mode=(SELECT REPLACE(@@sql_mode,'ONLY_FULL_GROUP_BY',''));
                              CREATE USER IF NOT EXISTS %(user)s@'%' IDENTIFIED BY %(pwd)s;
                              GRANT ALL PRIVILEGES ON *.* TO %(name)s@'%';
                              FLUSH PRIVILEGES;''', db)
            res = con.commit()
except:
    pass

    subprocess.run(['kamdbctl create'], shell=True)

try:
    with closing(mysqlcon.connect(host=db['host'],
                                  user=db['user'],
                                  password=db['pwd'],
                                  database=db['name'])) as con:
        with closing(con.cursor()) as cursor:
            cursor.execute('''ALTER TABLE location
                              ADD COLUMN locked INTEGER NOT NULL DEFAULT 0''')
            res = con.commit()
except:
    pass

kamRunCmd='kamailio -DD -E'

if os.getenv("SIP_DOMAIN"):
    kamRunCmd+= ' --alias {}'.format(os.getenv("SIP_DOMAIN"))

if os.getenv("PUBLIC_IP"):
    kamRunCmd+= ' --alias {}'.format(os.getenv("PUBLIC_IP"))

if os.getenv("LOCAL_IP"):
    kamRunCmd+= ' -l tcp:{}:5060'.format(os.getenv("LOCAL_IP"))
    kamRunCmd+= '/{}:5060'.format(os.getenv("PUBLIC_IP", os.getenv("LOCAL_IP")))
    kamRunCmd+= ' -l udp:{}:5060'.format(os.getenv("LOCAL_IP"))
    kamRunCmd+= '/{}:5060'.format(os.getenv("PUBLIC_IP", os.getenv("LOCAL_IP")))


kamRunCmd+= ' -A \'DBURL="mysql://{}:{}@{}/{}"\''.format(
                os.getenv("DBRWUSER"), os.getenv("DBRWPW"),
                os.getenv("DBHOST"), os.getenv("DBNAME"))

if os.getenv('TLS', 'False').lower() == 'true':
    kamRunCmd+= ' -A WITH_TLS'
    if os.getenv("LOCAL_IP"):
        kamRunCmd+= ' -l tls:{}:5061'.format(os.getenv("LOCAL_IP"))
        kamRunCmd+= '/{}:5061'.format(os.getenv("PUBLIC_IP", os.getenv("LOCAL_IP")))

if os.getenv('DEBUG_LEVEL') and os.getenv('DEBUG_LEVEL').isdigit():
        kamRunCmd+= ' -A \'DBGLEVEL={}\''.format(os.getenv("DEBUG_LEVEL"))

if os.getenv('ANTIFLOOD', 'False').lower() == 'true':
    kamRunCmd+= ' -A WITH_ANTIFLOOD'

print("Kamailio run command: {}".format(kamRunCmd), flush=True)

cmd = subprocess.Popen(kamRunCmd,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)

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


