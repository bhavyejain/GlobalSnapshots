CLIENT_PORTS = {"A": 9260, "B": 9261, "C": 9262, "D": 9263, "E": 9264}
CONNECTIONS = {"A" : {"B"}, "B" : {"A", "D"}, "C" : {"B"}, "D" : {"A", "B", "C", "E"}, "E" : {"B", "D"}}
BUFF_SIZE = 1024
HOST = '127.0.0.1'
DEF_DELAY = 3.00
TOKEN_HOLD_TIME = 1.00