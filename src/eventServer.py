import socket
import threading
import pynetstring
import sys

# Configuration
HOST = '0.0.0.0'
PORT = 4444
CONTROL_PORT = 5555
BUFFER_SIZE = 1024

Clients = []
ClientsLock = threading.Lock()
StopEvent = threading.Event()

def push(inDict, fromSock):
    with ClientsLock:
        for client in Clients:
            if client is serversocket or client is fromSock:
                continue
            try:
                print(f"Received input event: {inDict}", flush=True)
                client.send(inDict.rstrip())
            except Exception as e:
                print(f"Push error: {e}", flush=True)

def handleClient(clientSocket, clientAddress):
    print(f"Accepted connection from: {clientAddress}", flush=True)
    buffer = b""
    try:
        while not StopEvent.is_set():
            data = clientSocket.recv(BUFFER_SIZE)
            if not data:
                break
            buffer += data
            try:
                if buffer:
                    push(buffer, clientSocket)
                    buffer = b""
            except Exception as e:
                print(f"Netstring decoding error: {e}", flush=True)
                buffer = b""
    except Exception as e:
        print(f"Client error: {e}", flush=True)
    finally:
        with ClientsLock:
            if clientSocket in Clients:
                Clients.remove(clientSocket)
        clientSocket.close()
        print(f"Connection closed: {clientAddress}", flush=True)

def controlServer():
    """Listens on CONTROL_PORT and shuts down the server on receiving '/quit'."""
    controlSock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    controlSock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    controlSock.bind((HOST, CONTROL_PORT))
    controlSock.listen(1)
    print(f"Control server listening on port {CONTROL_PORT}", flush=True)

    while not StopEvent.is_set():
        try:
            controlSock.settimeout(1.0)  # Check periodically for StopEvent
            conn, addr = controlSock.accept()
            with conn:
                data = conn.recv(BUFFER_SIZE).decode("utf-8").strip()
                print(f"Event server control received: {data}", flush=True)
                if data == "/quit":
                    print("Shutdown command received. Stopping server...", flush=True)
                    StopEvent.set()
        except socket.timeout:
            continue
        except Exception as e:
            print(f"Event server control error: {e}", flush=True)
            break
    controlSock.close()

# --- Main server setup ---
serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
serversocket.bind((HOST, PORT))
serversocket.listen(10)

# Start control thread
threading.Thread(target=controlServer, daemon=True).start()

print("Server is listening for connections...\n", flush=True)

try:
    while not StopEvent.is_set():
        serversocket.settimeout(1.0)  # allows periodic check of StopEvent
        try:
            clientsocket, clientaddr = serversocket.accept()
            with ClientsLock:
                Clients.append(clientsocket)
            threading.Thread(target=handleClient, args=(clientsocket, clientaddr), daemon=True).start()
        except socket.timeout:
            continue
except KeyboardInterrupt:
    print("Interrupted by keyboard.", flush=True)

# --- Graceful shutdown ---
print("Shutting down server...", flush=True)
serversocket.close()
with ClientsLock:
    for c in Clients:
        try:
            c.shutdown(2)
            c.close()
        except:
            pass
sys.exit(0)
