#!/usr/bin/env python
import subprocess

cmd = subprocess.Popen('kamailio -DD -E', stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)

while True:
    line = cmd.stdout.readline()
    if line:
        logs = line.decode()
        try:
            if logs.find('ACC: call missed:') != -1:
                accLog = logs.split('ACC: call missed:')[1]
                accDict = dict(el.split("=") for el in accLog.split(";"))
                if accDict['code'] == '500':
                    print('Unregister locked gateway: ',accDict['dst_user'], '\n', flush=True)
                    userName = accDict['dst_user'].rsplit('-0x', 1)[0]
                    subprocess.run(['kamctl ul rm {}'.format(userName)], shell=True)
        except:
            print('ACC logs parsing error \n', flush=True)
        print(logs, end='', flush=True)


