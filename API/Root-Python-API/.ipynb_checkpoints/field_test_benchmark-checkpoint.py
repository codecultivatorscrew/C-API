######################################################################################
# ble_network_command | dst_node_addr |          message        |
#       5 byte        |     2 byte    | 3 byte opcode | payload |
#
# === Network Command  === (5 byte)
# 'NINFO' get network info
# 'SEND-' send message
# 'BCAST' broadcast message
# 'RST-R' reset root module
# 'ACT-C' get active node count
#
# '[GET]' get node data
# 
#
# === API opcode / message type (opcode) === (3 byte)
# 'ECH' for echo message, expecting copy
# 'CPY' for copy message on recived 'ECH'
# 'REQ' edge request
#
# 'NET' Network Information message
# 'NOD' Node Connecetd update message
# 'RST' root module reseted
# '[D]' node data
#
# 'TST' for field test test-flow
# 'TST|I|test_name' expecting copy on edge confirmed test initialization
# 'TST|S' start test
# 'TST|F' finish test
#
######################################################################################

# Test-Flow
# A network-measuring Python test program (not our Python server, but a lot of the same code).
# 1 -  Python test program send command to Edge-device (ras-pi) to change the test mode
# 2 - Ras-pi return confirm
# 3 - Python Bcast a pkt to start the current test and measures the metric
# 4 - Python Bcast a pkt to finish the current test
# 5 - Record Measurement

# For example: (connect 10 node speed)
# 1 - Python sends ‘Test-0’ to all edge device
# 2 - Ras-pi all confirm copy on changing test mode
# 3 - Python start timer and Broadcast ‘START’ to all ras-pi & reset ESP-root
# 4 - Ras-pi restart the ESP-edge
# 5 - Python stop timer when all 10 nodes are connected
# 6 - Python Broadcast ‘FINISH’ to stop the current test # no need for test-0 reconnect
# 7 - Record the Timestamp of each node connected 

import time
import json
from socket_api import Socket_Manager  # class object
from socket_api import craft_message_example, parseNodeAddr, encodeNodeAddr  # function
from opcode_subscribe import subscribe, unsubscribe

# globl variable so it can be accessed by all test and reused
network_node_amound = 0
current_test = ""
broadcast_confirmed_node = []
# this is for holding result from any callback function
# one should be enough since the test code is serial there is only one current_test, so only one callback function should be active
# if late response come in from old test, it the call back function should set to be ignored
result_from_callback = {}


def field_test_broadcast_confirm_callback(message: bytes):
    global broadcast_confirmed_node, current_test
    node_addr = parseNodeAddr(message[0:2])
    opcode = message[2:5] # subscriped opcode 'CPY'
    payload = message[5:]
    
    try:
        payload = payload.decode('utf-8')
    except:
        print(f"failed to decode payload {payload}")
        return
        
    print("[Callback] node_addr:",node_addr, ", opcode:", opcode.decode('utf-8'), ", payload:", payload)
    
    if payload[0] != "I":
        print(f"wrong copy message, not 'I' - test initialization")
        return
        
    test_name = payload[1:]
    print(f"test_name: '{test_name}', current_test: '{current_test}'")
    if test_name == current_test:
        broadcast_confirmed_node.append(node_addr)

def broadcast_initialization_and_wait_for_confirm(socket_api, test_name, test_parameter_bytes, node_amount, timeout):
    global network_node_amound, broadcast_confirmed_node, current_test
    broadcast_confirmed_node = []
    current_test = test_name
    
    # subscribe on copy message that will get sendback from edge 
    # after broadcasting 'ECH' message
    subscribe("CPY", field_test_broadcast_confirm_callback)
    
    # broadcast 'ECH' (echo) message - expecting copy from edge
    #            test  initialize  test_name
    message_str = "TST" + "I" + test_name
    message_byte = craft_message_example("BCAST", 0, message_str.encode() + test_parameter_bytes) 
    socket_api.socket_sent(message_byte)

    # timeout
    start_time = time.time()
    timeout = 10

    while len(broadcast_confirmed_node) < node_amount:
        current_time = time.time()
        if current_time - start_time > timeout:
            print(f"Faild to confirm {test_name} broadcast with edge device")
            print(f" - {len(broadcast_confirmed_node)} copied broadcast message")
            unsubscribe("CPY", field_test_broadcast_confirm_callback)
            return False
        
        time.sleep(0.1) # check every 0.1 second
    
    # recived all confirmation
    unsubscribe("CPY", field_test_broadcast_confirm_callback)
    return True

def send_command(socket_api, command: str, node_addr: int, payload: bytes) -> tuple[bool, bytes]:
    # send command and confirm executed successfully
    message = craft_message_example(command, node_addr, payload) 
    response = socket_api.socket_sent(message)
    if response[0:1] == b'F': # socket command faild
        error = response[1:]
        try:
            error = error.decode()
        except:
            pass
        print(f"Socket Command '{command}' failed, Error: {error}")
        return (False, error)
    
    # succeed
    response = response[1:]
    return (True, response)

def test_initialization(socket_api, test_name, test_parameter_bytes, node_amount, broadcast_timeout, node_addr):
    # broadcast 'TST|I|test_name' (test init) to initilize test on edge device
    success = broadcast_initialization_and_wait_for_confirm(socket_api, test_name, test_parameter_bytes, node_amount, broadcast_timeout)
    if not success:
        return False
    print(f" - Initialized Test on edge")

    # send 'TST|S' (test start) to edge device
    command = "BCAST"
    if node_amount == 1:
        command = "SEND-"

    print(f" - Starting Test on Node-{node_addr}, command: '{command}'")
    success, _ = send_command(socket_api, command, node_addr, "TSTS".encode())
    if not success:
        return False

    time.sleep(1) # Testing, TB Finished (remove) ----------------------------------------------------------------
    print(f" - Started Test on edge")

    return True # success

def test_termination(socket_api):
    # broadcast 'TST|F' (test finish) to edge device
    success, _ = send_command(socket_api, "BCAST", 0, "TSTF".encode()) 
    if not success:
        return False
    print(f" - Finished Test on edge by broadcast")
    return True

def get_N_Nodes(socket_api, node_amount):
    message_byte = craft_message_example("NSTAT", 0, b'') 
    data = socket_api.socket_sent(message_byte)
    error_code = data[0]
    payload = data[1:]
    
    if error_code != ord('S'):
        print("Failed to retrive node status from server: ", payload)
        return (None, "Failed to retrive node status")
        
    # Decode the received bytes
    network_status_json = payload.decode('utf-8')
    network_status = json.loads(network_status_json)

    network_node_amount = network_status["node_amount"]
    node_addr_list = network_status["node_addr_list"]
    node_status_list = network_status["node_status_list"]
    
    selected = []

    for i in range(network_node_amount):
        if node_status_list[i] == 1:
            selected.append(node_addr_list[i])
            
        if len(selected) == node_amount:
            return (selected, "Success")

    # no enough nodes in network
    return (None, "No enough nodes in network")

# =============== Testers ====================
def connect_N_node(socket_api, node_amount):
    # check if uart is running, root is runing, has 10 node
    # FLDTS
    global network_node_amound, broadcast_confirmed_node
    attempts = 0
    max_attempts = 3
    broadcast_timeout = 10
    conenct_node_timeout = 20
    node_addr = 0
    test_name = "TEST0" # to be renamed ------------------------------------------------------------------
    test_parameter_byte = b''
    
    # subscribe("[NET]", test_0_network_status_callback)
    # ----------- Test 0 -----------
    while attempts < max_attempts:
        attempts += 1
        print(f"\n===== Starting test-0 with attempt-{attempts}/{max_attempts} ===== ")

        if node_amount == 1 and node_addr == 0:
            # get a list of n nodes
            node_addr_list, error_msg = get_N_Nodes(socket_api, node_amount)
            if node_addr_list == None:
                print(error_msg)
                time.sleep(5) # allow some time for node to connect
                continue
            node_addr = node_addr_list[0]
        
        # broadcast to initialize and start test on edge
        success = test_initialization(socket_api, test_name, test_parameter_byte, node_amount, broadcast_timeout, node_addr)
        if not success:
            continue
        
        # Starting test
        # reset root
        root_online = False
        def wait_for_root_restart(data):
            nonlocal root_online # refer to the root_online defined above
            root_online = True
        
        subscribe("[R]", wait_for_root_restart)
        success, _ = send_command(socket_api, "CLEAN", 0, b'') 
        if not success:
            continue
        print(f" - Root resetting")
        time.sleep(2) # some buffer time before restart, allow reset work to be finished
        
        success, _ = send_command(socket_api, "RST-R", 0, b'') 
        if not success:
            continue
        print(f" - Root restarting")

        while root_online == False:
            pass
        print(f" - Root restarted, wating on edge connect back")
        unsubscribe("[R]", wait_for_root_restart)
        
        # check active node count on network
        start_time = time.time()
        current_time = start_time
        time_elapsed = 0
        active_count = 0
        time.sleep(0.1) # for testing------------------------------
        while active_count < node_amount:
            current_time = time.time()
            time_elapsed = current_time - start_time
            if time_elapsed > conenct_node_timeout:
                print(f"Timeout Trigered, failed to connect {node_amount} nodes in {conenct_node_timeout}")
                break
                
            success, response = send_command(socket_api, "ACT-C", 0, b'')
            new_active_count = response[0]
            if active_count != new_active_count:
                active_count = new_active_count
                print(f" - {active_count} node connected with {round(time_elapsed, 2)} second elapsed")
            
            time.sleep(0.1) # checking every 0.1 second
            
        # check if is a timeout that break the loop
        if active_count < node_amount:
            continue
        
        # finished the test on current attempt
        print(f"All {node_amount} node conneceted back, test finished")
        # log result
        attempts = max_attempts + 1
        break
    
    # test finished
    if attempts == max_attempts + 1:
        current_time = time.time()
        time_elapsed = current_time - start_time
        print("Connect N node Succeed, time: ", round(time_elapsed, 5) , "s")
        # print the result
    else:
        print("Connect N node Failed")
    print(f"\n===== Exiting test-0 =====\n\n")
    # ----------- Test 0 -----------


def RTT_tester(socket_api, node_amount, data_size, send_rate, duration):
    # check if uart is running, root is runing, has 10 node
    # FLDTS
    global network_node_amound, broadcast_confirmed_node
    attempts = 0
    max_attempts = 3
    broadcast_timeout = 10
    conenct_node_timeout = 20
    node_addr = 0
    test_name = "RTT--" # to be renamed ------------------------------------------------------------------
    test_parameter_byte = b''
    
    # ----------- Test -----------
    while attempts < max_attempts:
        attempts += 1
        print(f"\n===== Starting RTT_test ({data_size} bytes, {send_rate} Hz) to {node_amount} nodes with attempt-{attempts}/{max_attempts} ===== ")

        if node_amount == 1 and node_addr == 0:
            # get a list of n nodes
            node_addr_list, error_msg = get_N_Nodes(socket_api, node_amount)
            if node_addr_list == None:
                print(error_msg)
                time.sleep(5) # allow some time for node to connect
                continue
            node_addr = node_addr_list[0]
        
        # broadcast to initialize and start test on edge
        success = test_initialization(socket_api, test_name, test_parameter_byte, node_amount, broadcast_timeout, node_addr)
        if not success:
            continue
        
        # Starting test
        success, error_msg = ping_N_node(socket_api, node_amount, data_size, send_rate, duration)
        if not success:
            print(error_msg)
            continue
        
        # finished the test on current attempt
        print(f"All {node_amount} node conneceted back, test finished")
        # log result
        attempts = max_attempts + 1
        break
    
    # test finished
    if attempts == max_attempts + 1:
        print("Test Finished")
        # print the result
    else:
        print("Test Failed")
    print(f"\n===== Exiting test =====\n\n")
    # ----------- Test 0 -----------

# call test_initialize() before test
# asssume we populate the broadcast_confirmed_node[] first through test_initialize() before calling this function
# based on the test_initialize() functin's name it will becalled before this function.
def ping_N_node(socket_api, node_amount, data_size, send_rate, duration) -> tuple[bool, str]:
    # measure RTT and Pkt loss for sending
    # ping <node_amount> node, <data_size> bytes paket on <send_rate> over <time> second
    # assume the send_rate is how many time between each send
    # if is by HZ then uncomment the following code
    send_interval = 1/send_rate  # 1/Hz = second

    #initialize recorders
    ping_start_time_list = []
    ping_dict = {}
    for i in range(node_amount):
        ping_dict[broadcast_confirmed_node[i]] = [] # list of (pkt_number, end_time)  

    #  ------------ callback function ------------
    def ping_N_node_callback(message: bytes):
        # need to make sure the current test is still correct, if it's message from a old test, ignore it
        # if current_test != "Ping_N_Node":
        #     return
        nonlocal ping_dict
        
        end_time = time.time()
        node_addr = parseNodeAddr(message[0:2])
        opcode = message[2:5] # subscriped opcode 'CPY'
        pkt_number = parseNodeAddr(message[5:7])
        pkt_payload = message[7:]
        
        try:
            pkt_payload = pkt_payload.decode()
        except:
            print(f"failed to decode payload {payload}")
            return
        
        if pkt_payload[0] != "P":
            print(f"wrong copy message, not 'P' - ping response")
            return

        print(f"Node-{node_addr} pkt {pkt_number} returned")
        ping_dict[node_addr].append((pkt_number, end_time))
    #  ------------ callback function ------------
    
    subscribe("CPY", ping_N_node_callback)
    if data_size < 4: #  3 opcode + 2_byte pkt_number + payload size minimum of 1 'p'
        return (False, "Data size too small")
    pkt_payload = 'P' * (data_size-5) # minus 3 opcode + 2_byte pkt_number 
    pkt_payload_bytes = pkt_payload.encode()
    
    
    test_start_time = time.time()
    # while withiin the pinging time
    pkt_number = 0
    while time.time() - test_start_time < duration:
        # broadcast
        pkt_number_bytes = encodeNodeAddr(pkt_number)
        ping_message_bytes = "ECH".encode() + pkt_number_bytes + pkt_payload_bytes
        
        success, error_msg = send_command(socket_api, "BCAST", 0, ping_message_bytes) 
        if not success:
            return (False, error_msg)
        ping_start_time_list.append(time.time())
        
        pkt_number += 1
        time.sleep(send_interval)
    
    # leave the timeout_time for the last packet to return
    print(" - End of sending Ping request, Waiting for last response packet")
    time.sleep(5)
    print(" - computing result")
    # calculate and print the result of ping
    totoal_send_pkt = len(ping_start_time_list)
    for i in range(node_amount):
        node_addr = broadcast_confirmed_node[i]
        total_return_pkt = len(ping_dict[node_addr])
        
        total_time = 0
        for j in range(total_return_pkt):
            pkt_num, end_time = ping_dict[node_addr][j]
            start_time = ping_start_time_list[pkt_num]
            total_time += end_time - start_time

        pkt_lost = round((totoal_send_pkt - total_return_pkt) / totoal_send_pkt, 2)
        avg_rtt = 0
        if total_return_pkt != 0:
            avg_rtt = round(total_time / total_return_pkt, 3)
        print(f"  Node-{node_addr}, pkt_loss: {pkt_lost}%, AVG_RTT: {avg_rtt}")
    
    # reset dictionary and callback function that subscribed to "CPY" opcode
    unsubscribe("CPY", ping_N_node_callback)
    return (True, "S")

    
def request_test(node_amount, request_name):
    # measure RTT and Pkt loss for sending
    # ping <node_amount> node, <data_size> bytes paket on <send_rate> over <time> second
    
    global network_node_amound, broadcast_confirmed_node
    attempts = 0
    max_attempts = 3
    broadcast_timeout = 10
    node_addr = 0
    test_name = "TESTR" # to be renamed ------------------------------------------------------------------
    test_parameter_byte = b''
    
    if node_amount == 1:
        # get a list of n nodes
        node_addr_list, error_msg = get_N_Nodes(node_amount)
        if node_addr_list == None:
            print(error_msg)
            return
        node_addr = node_addr_list[0]
        
    while attempts < max_attempts:
        attempts += 1
        print(f"\n===== Starting '{request_name}' request_test on {node_amount} nodes with attempt-{attempts}/{max_attempts} ===== ")
        
        # Test Initialization
        success = test_initialization(socket_api, test_name, test_parameter_byte, node_amount, broadcast_timeout, node_addr)
        if not success:
            continue
        print(f"Edge will now send '{request_name}' request")
        
        # Test Body
        time.sleep(5) # requests from edge will show up on the other thread, need to monitor the traffic
        
        success = test_termination(socket_api)
        if not success:
            continue
        
        print(f"Request Test finished")
        # log result
        attempts = max_attempts + 1
        break
        
    # test finished
    if attempts == max_attempts + 1:
        current_time = time.time()
        time_elapsed = current_time - start_time
        print(f"'{request_name}' Request Test Succeed")
        # print the result
    else:
        print(f"'{request_name}' Request Test Failed")
    # ----------- request_test -----------

  
# data_update_test on n_node
def data_update_test(node_amount, data_size, edge_send_rate):
    global network_node_amound, broadcast_confirmed_node
    attempts = 0
    max_attempts = 3
    broadcast_timeout = 10
    node_addr = 0
    test_name = "TESTD" # to be renamed ------------------------------------------------------------------
    # 2 byte data size, 1 byte send rate
    test_parameter_byte = b'' + struct.pack('!H', data_size) + struct.pack('b', edge_send_rate % 255)
    
    if node_amount == 1:
        # get a list of n nodes
        node_addr_list, error_msg = get_N_Nodes(node_amount)
        if node_addr_list == None:
            print(error_msg)
            return
        node_addr = node_addr_list[0]
        
    while attempts < max_attempts:
        attempts += 1
        print(f"\n===== Starting data_update_test ({data_size} bytes, {edge_send_rate} Hz) on {node_amount} nodes with attempt-{attempts}/{max_attempts} ===== ")
        
        # Test Initialization
        success = test_initialization(socket_api, test_name, test_parameter_byte, node_amount, broadcast_timeout, node_addr)
        if not success:
            continue
        print(f"Edge will now send {data_size} bytes data update on {edge_send_rate} Hz")
        
        # Test Body, data update will be sened
        # TB Finished when we have edge check the data been sended by request data from server
        # for 30 second
        time.sleep(30)
        
        success = test_termination(socket_api)
        if not success:
            continue
            
        # finished the test on current attempt
        attempts = max_attempts + 1
        break
        
    # test finished
    if attempts == max_attempts + 1:
        current_time = time.time()
        time_elapsed = current_time - start_time
        print(f"Data Request Test Finished")
        # print the result
    else:
        print(f"Request Test Failed")
    # ----------- data_update_test -----------