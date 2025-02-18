#!/usr/bin/env python
from socket import socket, AF_INET, SOCK_STREAM, SOL_SOCKET, SO_REUSEADDR
import threading
import pynetstring

host = '0.0.0.0'
port = 4444
buf = 1024

addr = (host, port)

serversocket = socket(AF_INET, SOCK_STREAM)
serversocket.setsockopt(SOL_SOCKET, SO_REUSEADDR, 1)
serversocket.bind(addr)
serversocket.listen(10)

clients = [serversocket]

def push(inDict, fromSock):
    for i in clients:
        if i is serversocket or i is fromSock or not inDict:
            continue
        print('Received input event: '+ inDict, flush=True)
        try:
            i.send(pynetstring.encode(inDict))
        except:
            print('input event push error', flush=True)

def handler(clientsocket, clientaddr):
    print("Accepted connection from: ", clientaddr)
    while True:
        data = clientsocket.recv(1024)
        push(data.decode("utf-8").rstrip(), clientsocket)
        if "quit" in data.decode("utf-8") or not data:
            break

    clients.remove(clientsocket)
    clientsocket.close()

while True:
    try:
        print( "Server is listening for connections\n")
        clientsocket, clientaddr = serversocket.accept()
        clients.append(clientsocket)
        handlerThread = threading.Thread(target=handler, args=(clientsocket, clientaddr,))
        handlerThread.start()
    except KeyboardInterrupt: # Ctrl+C # FIXME: vraci "raise error(EBADF, 'Bad file descriptor')"
        print( "Closing server socket...")
        serversocket.close()
