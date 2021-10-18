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

    def decodeNetString(self, inStr):
        mDict = {}
        if inStr and len(inStr) > 0 :
            inStrLen = inStr[0:inStr.find(':')]
            resp = inStr.split(inStrLen+':')[1]
            mDict = json.loads(resp[0:len(resp)-1])

        return mDict

    def getStatus(self, sock, timeOut=None):
        received = ""
        dataLen = 0
        preRead = 8
        # Receive data from baresip
        try:
            received = (sock.recv(preRead)).decode("utf-8")
        except socket.timeout:
            # return exception message in netstring format
            retTxt = '{"event": true, "type": "TIME_OUT"}'
            return str(len(retTxt)) + ":" + retTxt + ","
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
            packet = sock.recv(readLen)
            dataLen -= readLen
            if not packet:
                break
            received = received + packet.decode("utf-8")

        return received

    def sendCommand(self, cmd):
        cmdStr = json.dumps(cmd)
        data = str(len(cmdStr))+':'+cmdStr+','
        res = []
        # Create a socket (SOCK_STREAM means a TCP socket)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            # Connect to server and send data
            sock.connect((self.host, self.port))
            sock.sendall(bytes(data,encoding="utf-8"))
            status = self.getStatus(sock)
            res.append(self.decodeNetString(status))
            if status.find('"event":') >= 0 :
                status = self.getStatus(sock)
                res.append(self.decodeNetString(status))
        except:
            return -1
        finally:
            sock.close()

        return res

    def getEvents(self, callBack, args, timeOut=None):
        res = []
        try:
            # Create a socket (SOCK_STREAM means a TCP socket)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeOut)
            # Connect to server and send data
            sock.connect((self.host, self.port))
            while True:
                status = self.getStatus(sock, timeOut)
                if status:
                    if callBack(self.decodeNetString(status), args):
                        break
        except:
            print("Get events loop abnormally stopped", file=sys.stderr, flush=True)
            print(traceback.format_exc(), file=sys.stderr, flush=True)
            return -1
        finally:
            sock.close()

        return res

