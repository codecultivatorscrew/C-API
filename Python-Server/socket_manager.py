import socket
import threading
import time
from datetime import datetime

class Socket_Manager():
    def __init__(self, server_listen_port, PACKET_SIZE):
        self.PACKET_SIZE = PACKET_SIZE
        self.server_listen_port = server_listen_port
        self.server_socket = None             # Listen for all socket connection
        self.server_listen_thread = None
        self.send_socket = None             # The Main communication Socket for python sending to C-API
        self.send_address = None
        self.callback_func = None
        self.disconnect = True
        self.initialize_socket()
    
    def initialize_socket(self):
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.bind(('localhost', self.server_listen_port))
        self.server_socket.settimeout(None)  # accept_connectiondont timeout when waiting for response
                    
    def run(self):
        print("Starting socket thread")
        self.socket_thread = threading.Thread(target=self.server_listening_thread, args=(), daemon=True)
        self.socket_thread.start()
        print("Started socket thread")

                
    def connect_send_socket(self): # -------------------- TB Finish --------------------------
        self.server_socket.listen(1) # 1 space in queue is enough
        # send_socket, send_address = self.server_socket.accept()
        
        # ====== inital extra handshake to confim it belong to our project =======
        # ====== verify is a send_socket (C_API's listen socket) =======
        # TB Finish
        # ------------ TB Review ------------------------
        print("disconnection: " + str(self.disconnect))
        while (self.disconnect == True):
            send_socket, send_address = self.server_socket.accept()
            print("here")
            data = send_socket.recv(self.PACKET_SIZE)
            print("data: ", data)
            if data != b'[syn]\x00':
                send_socket.send(b'[err]-listen_socket_disconnected')
                send_socket.close()
            else:
                print("connected to listen")
                send_socket.send(b'[ack]\x00')
                self.disconnect = False
        # ====== end of confirmation
        self.send_socket = send_socket
        self.send_address = send_address
        print(f"Connected with send:{send_address}")

    
    def server_listening_thread(self):
        print("=== Enter socket (server) listening thread === ")
        # connect send_socket
        self.connect_send_socket()
        
        # listen to socket sonnection for C-API data/message request
        self.server_socket.listen(5)
        print(f"Listening on 'localhost':{self.server_listen_port} for C-API socket connection")
        while True:
            #------TB Review : reconnection----------------
            if(self.disconnect == True):
                print("---------------------------reconnecting------------------------------")
                self.connect_send_socket()
            #----------------------------------------------
            client_socket, address = self.server_socket.accept()
            # print(f" - Request connection from C-API in {address} has been established.") # [Testing Log]
            
            request_handler_thread = threading.Thread(target=self.socket_handler, args=(client_socket,))
            request_handler_thread.start()


    def socket_handler(self, client_socket):
        # print("Starting new C-API socket request thread")  # [Testing Log]

        # read the request from C-API from socket
        data = client_socket.recv(self.PACKET_SIZE)
        # print("Received Request:", data.decode())

        # pass data to Net_Manager's function to handler and return the response
        response_bytes = self.callback_func(data)
        
        client_socket.send(response_bytes)
        client_socket.close()
    
    
    def attack_callback(self, callback_func):
        self.callback_func = callback_func
        print(f"[Socket] Successfully attached callback function, {type(self.callback_func)}")
        
        
    def send_data(self, data): # -------------------- TB Finish --------------------------
        print("sending data")
        if self.send_socket != None:
            # socket.sento(bytes, addr)
            print("send_data called")
            try:
                self.send_socket.sendall(data)
            except socket.error as e:
                err_no = e.errno
                error_str = e.strerror
                if(err_no == 32 or err_no == 104 or err_no == 111):
                    print("Client socket disconnected")
                    self.send_socket.close()
                    self.disconnect = True
                if err_no == 110:
                    print("Connection timeout")
        else:
            print("No socket connected")
            # implment attemps of reconnection