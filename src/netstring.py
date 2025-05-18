#!/usr/bin/env python

import socket
import sys
import json
import time
import signal
import traceback


class Netstring:
    host = "localhost"
    port = 4444

    def __init__(self, h, p):
        self.host = h
        self.port = p
        signal.signal(signal.SIGTERM,
                      lambda s,f :
                      subprocess.run(['echo "/quit" | netcat -q 1  {} 5555'.format(self.host)],
                                     shell=True))

    def decodeNetString(self, inStr):
        mDict = {}
        if inStr and len(inStr) > 0 :
            inStrLen = inStr[0:inStr.find(':')]
            resp = inStr.split(inStrLen+':')[1]
            try:
                mDict = resp[0:len(resp)-1]
                mDict = json.loads(mDict.replace('\\"',"'").replace('\\',''), strict=False)
            except:
                mDict = {'event': 'null', 'type': 'null'}
                print("Failed to load string as JSON", file=sys.stdout, flush=True)

        return mDict

    def __getStatus(self):
        received = ""
        dataLen = 0
        preRead = 8
        # Receive data from baresip
        try:
            received = (self._sock.recv(preRead)).decode("utf-8")
            while len(received) > 0 and not received[0].isdigit():
                received = received[1:]
                preRead-=1
            preLen = received.find(':')
            if preLen >= 0:
                dataLen = preLen+ 2 + int(received[0:preLen]) - preRead
            while dataLen > 0:
                readLen = dataLen//1024
                if readLen==0:
                    readLen=dataLen%1024
                else:
                    readLen = 1024
                packet = self._sock.recv(readLen)
                dataLen -= readLen
                if not packet:
                    break
                received = received + packet.decode("utf-8")
        except socket.timeout:
            # return exception message in netstring format
            retTxt = '{"event": true, "type": "TIME_OUT"}'
            return str(len(retTxt)) + ":" + retTxt + ","
        except Exception as e:
                    print("Failed to get status", file=sys.stdout, flush=True)

        return received

    def __sendCommand(self, cmd):
        cmdStr = json.dumps(cmd)
        data = str(len(cmdStr))+':'+cmdStr+','
        self._sock.sendall(bytes(data,encoding="utf-8"))


    def getEvents(self, callBack, args, timeOut=None):
        try:
            # Create a socket (SOCK_STREAM means a TCP socket)
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            # Connect to server and send data
            self._sock.connect((self.host, self.port))
            self._sock.settimeout(timeOut)
            while True:
                status = self.decodeNetString(self.__getStatus())
                if not status:
                    break
                if "event" in status:
                    cmd = callBack(status, args)
                    if cmd:
                        self.__sendCommand(cmd)
        except:
            print("Get events loop abnormally stopped", file=sys.stdout, flush=True)
            print(traceback.format_exc(), file=sys.stdout, flush=True)
        finally:
            self._sock.close()


