#!/usr/bin/env python

import socket
import sys
import json
import time

class Netstring:
    host = "localhost"
    port = 4444

    def __init__(self, h, p):
        self.host = h
        self.port = p

    def decodeNetString(self, inStr):
        inStrLen = inStr[0:inStr.find(':')]
        resp = inStr.split(inStrLen+':')[1]
        mDict = json.loads(resp[0:len(resp)-1])

        return mDict

    def getStatus(self, sock):
        received = ""
        # Receive data from baresip
        preRead = 8
        received = (sock.recv(preRead)).decode("utf-8")
        while not received[0].isdigit():
            received = received[1:]
            preRead-=1
        preLen = received.find(':')
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

    def getEvent(self):
        res = []
        # Create a socket (SOCK_STREAM means a TCP socket)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            # Connect to server and send data
            sock.connect((self.host, self.port))
            while True:
                status = self.getStatus(sock)
                print(self.decodeNetString(status))
        except:
            return -1
        finally:
            sock.close()

        return res

