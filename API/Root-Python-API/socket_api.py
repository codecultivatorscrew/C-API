import threading
import socket
import time
import select
import struct
import errno
from datetime import datetime

# define constents
SOCKET_OPCODE_LEN = 5     # can be veried base on need
SOCKET_NODE_ADDR_LEN = 2  # need to be 2
BLE_MESH_BOARDCAST_ADDR = 255
socket_op_amount = 2
PORT = 6001
SERVER_PORT = 5001
host = 'localhost'
# example
# node_addr = struct.unpack('!H', node_addr)[0] # unpack 2 byte and converts them from network byte order to host byte order
# binary_data = struct.pack('!H', node_addr) # pack it back
SOCKET_OPCODE = [
    "[REQ]",
    "EMPTY"
]
class Socket_Manager():
    def __init__(self, server_addr, client_socket_callback):
        # set up the parameters
        self.client_socket_callback = client_socket_callback
        self.is_listening_connected = False
        if(server_addr == None):
            self.server_addr = (host, SERVER_PORT)
        else:
            self.server_addr = server_addr
        
            
    def run_socket_listen_thread(self):
        # creat threads, attach callback
        self.socket_thread = threading.Thread(target=self.socket_listening_thread, args=(), daemon=True)
        self.socket_thread.start()
    
    def setup_listen_connection(self):
        while (not self.is_listening_connected):
            try:
                listen_socket = self.connect_socket()
                if listen_socket == None:
                    time.sleep(2)
                    continue
                listen_socket.send(b'[syn]\x00')
                print("sent syn")
                handshake_msg = listen_socket.recv(6)
                print(f"received: {handshake_msg.decode()}")
                if handshake_msg == b'[ack]\x00':
                    self.is_listening_connected = True
                    return listen_socket
            except socket.error as e:
                print(f"Error: {e}")
                listen_socket.close()
                time.sleep(2)
        print("listen connection established")
        
    def socket_listening_thread(self):
        # actual thread function responsible for
        # - connect main listen socket
        # - triger callback when there is message
        # - reconnect the main listen socket when fail
        # - close the socket when finish (use finally so it close on exception as well) <- can't use finally because it's within the whie loop
        # hanshake and connect the socket
        listen_socket = self.setup_listen_connection()
        while(1):
            try:
                data = listen_socket.recv(1024)
                if not data:
                    print("Connection closed")
                    self.is_listening_connected = False
                    listen_socket.close()
                    listen_socket = self.setup_listen_connection()
                self.client_socket_callback(data)
            except socket.error as e:
                print(f"Error: {e}")
                listen_socket.close()
                self.is_listening_connected = False
                listen_socket = self.setup_listen_connection()
        #I need to figure out how to properly close the socket when process kill itself
        listen_socket.close()           

    
    def socket_sent(self, data: bytes) -> bytes:
        # return the responsed bytes or Fail bytes
        # connect a new one-time use send socket
        # what to do if it doesn't expect response, for example the resposne to edge nodes's request
        try:
            send_socket = self.connect_socket()
            timeout = 5
            if(send_socket == None):
                return b'f'
            send_socket.send(data)
            print("data sent through send socket")
            ready,_,_ = select.select([send_socket], [], [], timeout)
            if not ready:
                print("Timeout occurred")
                send_socket.close()
                return b'f'
            else:
                # If ready, read the response
                response = send_socket.recv(1024)
                print(f"Received response: {response}") 
                send_socket.close()       
            return response
        except socket.error as e:
            send_socket.close()
            print(f"Socket error: {e}")
            return b'f'
    
    def connect_socket(self) -> socket.socket:
        new_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            new_socket.connect(self.server_addr)
        except socket.error as e:
            print(f"Error: {e}")
            return None
        return new_socket
    
# why this need a self in the parameter, it's not in a class
def craft_message_example( socket_opcode, node_addr, msg_payload) -> bytes:
    # return the bytes of crafted message
    node_addr = struct.pack('!H', node_addr)
    message = socket_opcode.encode() + node_addr + msg_payload.encode()
    print(message)
    return message
   
# other utility function provide by our API

def getOpCodeNum(opcode):
    for i in range(socket_op_amount):
        if opcode == SOCKET_OPCODE[i]:
            return i
    return -1

def parseNodeAddr(addr_bytes: bytes):
    # parse 2 byte into number
    return struct.unpack('!H', addr_bytes)[0]