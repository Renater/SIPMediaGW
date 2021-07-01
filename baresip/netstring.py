#!/usr/bin/env python

import socket
import sys
import json
import time

HOST, PORT = "localhost", 4444

def decodeNetString(inStr):
  inStrLen = inStr[0:inStr.find(':')]
  resp = inStr.split(inStrLen+':')[1]
  mDict = json.loads(resp[0:len(resp)-1])

  return mDict

def getStatus(sock):
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

def sendCommand(cmd):
  cmdStr = json.dumps(cmd)
  data = str(len(cmdStr))+':'+cmdStr+','

  res = []
  # Create a socket (SOCK_STREAM means a TCP socket)
  sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  try:
  # Connect to server and send data
    sock.connect((HOST, PORT))
    sock.sendall(bytes(data,encoding="utf-8"))
    status = getStatus(sock)
    res.append(decodeNetString(status)) 

    if 'event' in status:
      status = getStatus(sock)
      res.append(decodeNetString(status))

  except:
    return -1

  finally:
    sock.close()

  return res

def getEvent():

  res = []
  # Create a socket (SOCK_STREAM means a TCP socket)
  sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
  try:
  # Connect to server and send data
    sock.connect((HOST, PORT))

    while True:
      status = getStatus(sock)
      print(decodeNetString(status))

  except:
    return -1

  finally:
    sock.close()

  return res

