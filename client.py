import socket
import threading
import config
import sys
import time
from threading import Lock
from utils import Colors as c
from utils import ClientStore, Message, Consts
import pickle
from queue import Queue
import random

my_client_name = ""
send_lock = Lock()
incoming_connections = {}
outgoing_connections = {}
local_state = Consts.WITHOUT_TOKEN
token_delivered_time = 0
token_drop_probability = 0 # out of 100
incoming_message_queues = {}

# assuming options is a dict
# prob is the probability is losing
def select_channel(options, prob=0):
    # either None or a key
    prob = int(prob)
    if prob>0 and random.randint(0, 100)<prob:
        return None
    return random.choice(list(options.keys()))

def handle_token():
    global local_state
    while True:
        if local_state == Consts.WITHOUT_TOKEN:
            time.sleep(0.5)
        else:
            delta1 = round((time.time() -  token_delivered_time), 2)
            delta2 = round((config.TOKEN_HOLD_TIME - delta1), 2) if delta1 < config.TOKEN_HOLD_TIME else 0
            time.sleep(delta2)
            channel = select_channel(outgoing_connections, token_drop_probability)
            with send_lock:
                local_state = Consts.WITHOUT_TOKEN
                if channel != None:
                    token = Message(message_type=Consts.TOKEN, from_pid=my_client_name, to_pid=channel)
                    print(f'{c.YELLOW}Sending TOKEN to {channel}{c.ENDC}')
                    encoded_token = pickle.dumps(token)
                    outgoing_connections[channel].sendall(encoded_token)
                else:
                    print(f"{c.FAILED}Token Dropped!{c.ENDC}")

def handle_cli(client, client_id):
    global local_state, snap_store, token_drop_probability
    client.sendall(bytes(f'Client {my_client_name} connected', "utf-8"))
    while True:
        try:
            message = client.recv(1024).decode()
            if message:
                print(f'{c.VIOLET}{client_id}{c.ENDC}: {message}')
                if message == "TOKEN":
                    local_state = Consts.WITH_TOKEN
                    print(f'{c.SUCCESS}TOKEN GENERATED{c.ENDC}')
                elif message == "SNAPSHOT":
                    marker_id = snap_store.initiate_self_global_snapshot()
                    print(f'{c.VIOLET}--- Initiate Global Snapshot With Marker {marker_id} ---{c.ENDC}')
                    with send_lock:
                        # record local state
                        print(f'Recording local state {local_state.value}')
                        snap_store.start_a_local_snap_store(marker_id=marker_id, state=local_state)
                        # Propagate the marker
                        print(f'Propagating marker {marker_id}...')
                        for client_name, connection in outgoing_connections.items():
                            prop_message = Message(message_type=Consts.MARKER, from_pid=my_client_name, to_pid=client_name, marker_id=marker_id)
                            print(f'{c.YELLOW}Sending {prop_message.__str__()} to {client_name}{c.ENDC}')
                            encoded_prop_message = pickle.dumps(prop_message)
                            connection.sendall(encoded_prop_message)
                elif message.startswith("DROP"):
                    cmd = message.split()
                    token_drop_probability = int(cmd[1])
                    print(f'Token drop probability set to {token_drop_probability}%')
            else:
                print(f'handle_cli# Closing connection to {client_id}')
                client.close()
                break
        except Exception as e:
            print(f'{c.ERROR}handle_cli# Exception thrown in {client_id} thread!{c.ENDC}')
            print(f'Exception: {e.__str__()}, Traceback: {e.__traceback__()}')

def handle_incoming_snap(client, client_id):
    global snap_store
    snap_raw = client.recv(config.SNAP_BUFF_SIZE)
    snap = pickle.loads(snap_raw) # object of class Message
    print(f'{c.BLUE}Received {snap.__str__()}{c.ENDC}')
    snap_store.update_global_snapshot(snap)
    client.close()

def handle_marker_message(conn_name, message):
    global snap_store, local_state
    if snap_store.is_a_new_marker(message.marker_id):
        print(f'Starting new local snapshot for marker {message.marker_id}...')
        with send_lock:
            snap_store.start_a_local_snap_store(marker_id=message.marker_id, state=local_state)
            # Propagate the marker
            print(f'Propagating marker {message.marker_id}...')
            for client_name, connection in outgoing_connections.items():
                prop_message = Message(message_type=Consts.MARKER, from_pid=my_client_name, to_pid=client_name, marker_id=message.marker_id)
                print(f'{c.YELLOW}Sending {prop_message.__str__()} to {client_name}{c.ENDC}')
                encoded_prop_message = pickle.dumps(prop_message)
                connection.sendall(encoded_prop_message)
    marker_id = snap_store.handle_incoming_channel_message(channel=conn_name, message=message)
    if marker_id != None:
        print(f'Completed local snapshot for marker {marker_id}!')
        client, snap = snap_store.generate_message_for_snap_send(marker_id=marker_id)
        if snap != None:
            # Send the snapshot to requesting client
            temp_conn = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            temp_conn.connect((config.HOST, config.CLIENT_PORTS[client]))
            temp_conn.sendall(bytes("SNAP", "utf-8"))
            encoded_snap = pickle.dumps(snap)
            time.sleep(0.5)
            print(f'{c.YELLOW}Sending {snap.__str__()} to {client}{c.ENDC}')
            temp_conn.sendall(encoded_snap)
            temp_conn.close()

def process_channel_messages(conn_name):
    global local_state, incoming_message_queues, snap_store, token_delivered_time
    while True:
        if not incoming_message_queues[conn_name].empty():
            msg = incoming_message_queues[conn_name].get()
            delta1 = round((time.time() -  msg[0]), 2)
            delta2 = round((config.DEF_DELAY - delta1), 2) if delta1 < config.DEF_DELAY else 0
            time.sleep(delta2) # deliver the message total DEF_DELAY time after receipt
            if msg[1].message_type == Consts.MARKER:
                print(f'{c.BLUE}Received {c.ENDC}' + msg[1].__str__() + f'{c.BLUE} from {conn_name}{c.ENDC}')
                handle_marker_message(conn_name, msg[1])
            elif msg[1].message_type == Consts.TOKEN:
                print(f'{c.BLUE}Received {c.ENDC}' + "TOKEN" + f'{c.BLUE} from {conn_name}{c.ENDC}')
                local_state = Consts.WITH_TOKEN
                token_delivered_time = round(time.time(), 2)
                snap_store.handle_incoming_channel_message(channel=conn_name, message=msg[1])
        else:
            time.sleep(1)

def handle_client(client, conn_name):
    global incoming_message_queues
    client.sendall(bytes(f'Client {my_client_name} connected', "utf-8"))
    thread = threading.Thread(target=process_channel_messages, args=(conn_name, ))
    thread.start()
    while True:
        try:
            raw_message = client.recv(config.BUFF_SIZE)
            if raw_message:
                message = pickle.loads(raw_message)
                incoming_message_queues[conn_name].put((round(time.time(), 2), message))
            else:
                print(f'handle_client# Closing connection {conn_name}')
                client.close()
                break
        except Exception as e:
            print(f'{c.ERROR}handle_client# Exception thrown in {conn_name} thread!{c.ENDC}')
            print(f'Exception: {e.__str__()}, Traceback: {e.__traceback__()}')

def establish_outgoing_connections():
    time.sleep(5)
    for client_id in config.CONNECTIONS[my_client_name]:
        print(f'startup# Connecting to {client_id}...')
        try:
            conn_name = f'{client_id}'
            outgoing_connections[conn_name] = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            outgoing_connections[conn_name].connect((config.HOST, config.CLIENT_PORTS[client_id]))
            outgoing_connections[conn_name].setblocking(True)
            outgoing_connections[conn_name].sendall(bytes(my_client_name, "utf-8"))
            print(f"startup# {outgoing_connections[conn_name].recv(config.BUFF_SIZE).decode()}")
        except:
            print(f'{c.ERROR}startup# Failed to connect to {client_id}!{c.ENDC}')
    print(f'================= STARTUP COMPLETE =================')

def receive():
    global snap_store
    while True:
        # Accept Connection
        client, addr = mySocket.accept()
        client.setblocking(True)
        # A/B/C/D/E
        client_id = client.recv(1024).decode()
        print(f"receive# Connecting with {client_id}...")
        
        if client_id == "CLI":
            thread = threading.Thread(target=handle_cli, args=(client, client_id, ))
            thread.start()
        else:
            conn_name = f'{client_id}'
            if conn_name == "SNAP":
                thread = threading.Thread(target=handle_incoming_snap, args=(client, client_id, ))
                thread.start()
            else:
                channel_name = snap_store.add_incoming_connection(client_id)
                incoming_connections[channel_name] = client
                incoming_message_queues[channel_name] = Queue(0)
                thread = threading.Thread(target=handle_client, args=(client, channel_name, ))
                thread.start()

if __name__ == "__main__":

    my_client_name = sys.argv[1]

    global snap_store
    snap_store = ClientStore(my_client_name)

    print(f'================= BEGIN STARTUP =================')
    print(f'startup# Setting up Client {my_client_name}...')

    connection_thread = threading.Thread(target=establish_outgoing_connections, args=())
    connection_thread.start()

    token_worker_thread = threading.Thread(target=handle_token, args=())
    token_worker_thread.start()

    mySocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    mySocket.bind((config.HOST, config.CLIENT_PORTS[my_client_name]))
    mySocket.listen(10)
    
    print('Listening for new connections...')
    receive()