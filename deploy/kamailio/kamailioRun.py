#!/usr/bin/env python3
import os
import subprocess
import sys
import time
from contextlib import closing
import mysql.connector as mysqlcon
from configparser import ConfigParser

parser = ConfigParser()
parser.optionxform = str
with open("/etc/kamailio/kamctlrc") as stream:
    parser.read_string("[kamctlrc]\n" + stream.read())
kamctlrc = dict(parser.items("kamctlrc"))
kamctlrc['DBHOST'] = os.getenv('MYSQL_HOST') or kamctlrc['DBHOST']
kamctlrc['DBROOTPW'] = os.getenv('MYSQL_ROOT_PASSWORD') or kamctlrc['DBROOTPW']
with open("/etc/kamailio/kamctlrc", 'w') as f:
    for key, value in kamctlrc.items():
        f.write('%s=%s\n' % (key, value.strip('"')))
        kamctlrc[key] = value.strip('"')

def unlock(dstUser):
    with closing(mysqlcon.connect(host=kamctlrc['DBHOST'],
                                  user=kamctlrc['DBRWUSER'],
                                  password=kamctlrc['DBRWPW'],
                                  database=kamctlrc['DBNAME'])) as con:
        with closing(con.cursor()) as cursor:
            cursor.execute('''UPDATE location SET locked = 0
                              WHERE  contact LIKE CONCAT('%',%s,'%');''',
                           (dstUser,))
            res = con.commit()

# At boot, Docker starts the containers in any order, so the database may not answer yet, and
# Kamailio stops when a module cannot connect while it initialises.
def waitForDatabase(timeout):
    deadline = time.time() + timeout
    while True:
        try:
            with closing(mysqlcon.connect(host=kamctlrc['DBHOST'],
                                          user='root',
                                          password=kamctlrc['DBROOTPW'],
                                          connection_timeout=5)):
                return True
        except mysqlcon.Error as e:
            # A refused login comes from a database that answers.
            if e.errno in (1044, 1045):
                return True
            if time.time() > deadline:
                print('The database {} does not answer after {} s: {}'.format(
                      kamctlrc['DBHOST'], timeout, e), flush=True)
                return False
            print('Waiting for the database {}: {}'.format(kamctlrc['DBHOST'], e), flush=True)
            time.sleep(3)

if not waitForDatabase(int(os.getenv('DB_WAIT_SECONDS') or 180)):
    sys.exit(1)

try:
    with closing(mysqlcon.connect(host=kamctlrc['DBHOST'],
                                  user='root',
                                  password=kamctlrc['DBROOTPW'])) as con:
        with closing(con.cursor()) as cursor:
            cursor.execute('''SET PERSIST sql_mode=(SELECT REPLACE(@@sql_mode,'ONLY_FULL_GROUP_BY',''));
                              CREATE USER IF NOT EXISTS %(DBRWUSER)s@'%' IDENTIFIED BY %(DBRWPW)s;
                              GRANT ALL PRIVILEGES ON *.* TO %(DBNAME)s@'%';
                              FLUSH PRIVILEGES;''', kamctlrc)
            res = con.commit()
except:
    pass

    subprocess.run(['kamdbctl create'], shell=True)

try:
    with closing(mysqlcon.connect(host=kamctlrc['DBHOST'],
                                  user=kamctlrc['DBRWUSER'],
                                  password=kamctlrc['DBRWPW'],
                                  database=kamctlrc['DBNAME'])) as con:
        with closing(con.cursor()) as cursor:
            cursor.execute('''ALTER TABLE location
                              ADD COLUMN locked INTEGER NOT NULL DEFAULT 0,
                              ADD COLUMN to_stop INTEGER NOT NULL DEFAULT 0;''')
            res = con.commit()
except:
    pass

kamRunCmd='kamailio -DD -E'

for sipDomain in os.getenv("SIP_DOMAIN", "").split(","):
    if sipDomain.strip():
        kamRunCmd+= ' --alias {}'.format(sipDomain.strip())

if os.getenv("PUBLIC_IP"):
    kamRunCmd+= ' --alias {}'.format(os.getenv("PUBLIC_IP"))

if os.getenv("LOCAL_IP"):
    kamRunCmd+= ' -l tcp:{}:5060'.format(os.getenv("LOCAL_IP"))
    kamRunCmd+= '/{}:5060'.format(os.getenv("PUBLIC_IP", os.getenv("LOCAL_IP")))
    kamRunCmd+= ' -l udp:{}:5060'.format(os.getenv("LOCAL_IP"))
    kamRunCmd+= '/{}:5060'.format(os.getenv("PUBLIC_IP", os.getenv("LOCAL_IP")))


kamRunCmd+= ' -A \'DBURL="mysql://{}:{}@{}/{}"\''.format(
                kamctlrc['DBRWUSER'], kamctlrc['DBRWPW'],
                kamctlrc['DBHOST'], kamctlrc['DBNAME'])

if os.getenv('TLS', 'False').lower() == 'true':
    kamRunCmd+= ' -A WITH_TLS'
    if os.getenv("LOCAL_IP"):
        kamRunCmd+= ' -l tls:{}:5061'.format(os.getenv("LOCAL_IP"))
        kamRunCmd+= '/{}:5061'.format(os.getenv("PUBLIC_IP", os.getenv("LOCAL_IP")))

if os.getenv('DEBUG_LEVEL') and os.getenv('DEBUG_LEVEL').isdigit():
        kamRunCmd+= ' -A \'DBGLEVEL={}\''.format(os.getenv("DEBUG_LEVEL"))

if os.getenv('HEPLIFY_SRV'):
        kamRunCmd+= ' -A WITH_HOMER'
        kamRunCmd+= ' -A \'HEPURI="sip:{}:9060"\''.format(os.getenv("HEPLIFY_SRV"))

if os.getenv('ANTIFLOOD', 'False').lower() == 'true':
    kamRunCmd+= ' -A WITH_ANTIFLOOD'

if os.getenv('IPAUTH', 'False').lower() == 'true':
    kamRunCmd+= ' -A WITH_IPAUTH'

print("Kamailio run command: {}".format(kamRunCmd), flush=True)

cmd = subprocess.Popen(kamRunCmd,
                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)

for line in iter(cmd.stdout.readline, b''):
    logs = line.decode(errors='replace')
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

# Kamailio has stopped. Leaving makes the container stop, so that its restart policy starts it again.
code = cmd.wait()
print('Kamailio stopped with exit code {}'.format(code), flush=True)
sys.exit(code or 1)


