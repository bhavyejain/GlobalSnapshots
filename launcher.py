import subprocess
import applescript
import os
import time
import socket
import config
import threading
import sys
from utils_ import Colors as c

subprocess.call(['chmod', '+x', 'startup.sh'])

pwd = os.getcwd()
print(f"================= {c.SELECTED}STARTING GLOBAL SNAPSHOT SIMULATOR{c.ENDC} =================")

for client in config.CLIENT_PORTS.keys():
    print(f'Starting {client}...')
    applescript.tell.app("Terminal",f'do script "{pwd}/startup.sh {client}"')
    time.sleep(0.2)

client_name = "CLI"

connections = {}

def receive(app):
    app.sendall(bytes(f'Client {client_name} connected', "utf-8"))
    while True:
        try:
            message = app.recv(config.BUFF_SIZE).decode()
            if not message:
                app.close()
                break
        except:
            app.close()
            break

def execute_command(seg_cmd):
    op_type = seg_cmd[0]

    if op_type == '#':
        return
    
    elif op_type == "wait":
        input(f"Press {c.BLINK}ENTER{c.ENDC} to continue simulation...")
    
    elif op_type == "token":
        client = seg_cmd[1]
        connections[client].sendall(bytes("TOKEN", "utf-8"))
    
    elif op_type == "snapshot":
        client = seg_cmd[1]
        connections[client].sendall(bytes("SNAPSHOT", "utf-8"))
    
    elif op_type == "drop":
        client = seg_cmd[1]
        probability = seg_cmd[2]
        connections[client].sendall(bytes(f"DROP {probability}", "utf-8"))
    
    elif op_type == "delay":
        t = float(seg_cmd[1])
        time.sleep(t)
    
    else:
        print(f'{c.ERROR}Invalid command!{c.ENDC}')

def send():
    while True:
        command = input(">>> ").strip()
        if command != "":
            seg_cmd = command.split()
            op_type = seg_cmd[0]

            if op_type == "simulate":
                print('========== STARTING SIMULATION ==========')
                with open('simulate.txt') as f:
                    start_time = time.time()
                    for line in f.readlines():
                        if line.strip() != "":
                            if line.startswith('#'):
                                print(f'{c.VIOLET}{line}{c.ENDC}')
                            else:
                                print(f'{line}')
                            seg = line.strip().split()
                            execute_command(seg)
                    end_time = time.time()
                    elapsed_time = end_time - start_time
                    print(f'{c.BLUE}Execution time: {elapsed_time} seconds{c.ENDC}')
                print('========== SIMULATION COMPLETE ==========')
            
            elif op_type == "exit":
                for connection in connections.values():
                    # connection.sendall(bytes("EXIT", "utf-8"))
                    connection.close()
                sys.exit(0)

            else:
                execute_command(seg_cmd)

def connect_to(name, port):
    print(f'startup# Connecting to client {name}...')
    connections[name] = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    connections[name].setblocking(True)
    connections[name].connect((config.HOST, port))
    connections[name].sendall(bytes(client_name, "utf-8"))
    print(f"startup# {connections[name].recv(config.BUFF_SIZE).decode()}")
    thread = threading.Thread(target=receive, args=(connections[name],))
    thread.start()

if __name__ == "__main__":

    for client, port in config.CLIENT_PORTS.items():
        connect_to(client, port)

    print(f"================= {c.SELECTED}SETUP COMPLETE{c.ENDC} =================")
    send()