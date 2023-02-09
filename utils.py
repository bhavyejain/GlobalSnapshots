from enum import Enum
import random
import pickle
import config
 
class Consts(Enum):
    PORT = "PORT"
    CONNECTION = "CONNECTION"
    MARKER = "MARKER" # for sending marker
    TOKEN = "TOKEN" # for sending token
    SNAP = "SNAP" # for sending snapshot from client
    WITH_TOKEN = "WITH_TOKEN"
    WITHOUT_TOKEN = "WITHOUT_TOKEN"

CLIENT_COUNT = len(config.CLIENT_PORTS)

# Usage of pickle
# convert obj to bytes - bytes = pickle.dumps(obj)
# convert bytes to obj - obj = pickle.loads(bytes)

# assuming options is a dict
# prob is the probability is losing
def select_channel(options, prob=0):
    # either None or a key
    prob = int(prob)
    if prob>0 and random.randint(0, 100)<prob:
        return None
    return random.choice(list(options.keys()))

class Message:
    # message_type can be MARKER, TOKEN, SNAP
    # from_pid has to be one of the clients
    # marker_id - tuple(pid, seq)
    # data - snapshot for SNAP message
    def __init__(self, message_type, from_pid, to_pid, marker_id=None, data=None):
        self.message_type = message_type
        self.from_pid = from_pid
        self.to_pid = to_pid
        self.marker_id = marker_id
        self.data = data
    
    def __str__(self):
        if self.message_type==Consts.TOKEN:
            return "{} sent from {} to {}".format(self.message_type.value, self.from_pid, self.to_pid)
        elif self.message_type==Consts.MARKER:
            return "{} - {} sent from {} to {}".format(self.message_type.value, self.marker_id, self.from_pid, self.to_pid)
        else:
            return "{} sent from {} with marker id as {} to {}".format(self.message_type.value, self.from_pid, self.marker_id, self.to_pid)

class LocalSnapshot:
    # class to track the local state of a client for a particular marker_id
    # state can be WITH_TOKEN or WITHOUT_TOKEN
    
    def __init__(self, state):
        self.state = state
        self.channel_data = {}

    def add_info(self, channel, message):
        self.channel_data[channel].append(message)

class GlobalSnapShot:
    
    def __init__(self, marker_id):
        self.marker_id = marker_id
        self.client_data = {}
        self.channel_data = {}
        self.update_complete = False
    
    # this returns true if this is the last client to have been added 
    def add_info(self, from_pid, snap=LocalSnapshot(Consts.WITHOUT_TOKEN, None)):
        self.client_data[from_pid] = snap.state
        for channel, data in snap.channel_data.items():
            if channel not in self.channel_data:
                self.channel_data[channel] = []
            # this will have something like TOKEN sent from A to B
            self.channel_data[channel].append(data)
        if len(self.client_data)==CLIENT_COUNT:
            update_complete = True
        return update_complete
    
    def __str__(self):
        output = "Marker ID - {}\n".format(self.marker_id)
        output += "Client Store - \n"
        output += "\n".join(["{} : {}".format(key, val) for key,val in self.client_data.items()])
        output += "\nChannel Store - \n"
        output += "\n".join(["{} : {}".format(key, ", ".join([str(x) for x in val])) for key,val in self.channel_data.items()])
        return output

class ClientStore:
    
    def __init__(self, pid):
        self.pid = pid
        self.channel_marker_store = dict() # all incoming channels, key - channel, value - set of markers bring tracked
        # key marker_id, value GlobalSnapshot
        self.global_snap_store = dict() # global stores this client started
        # key marker_id, value LocalSnapshot
        self.local_snap_store = dict() # local stores of all snaps being tracked
        self.active_markers = set()
    
    # make sure you call this only at the start of the setup and not when someone sends snap
    def add_incoming_connection(self, from_pid):
        # add the entry to marker store so that client track which marker data to track from that channel
        # this gives something like B->A
        key = "{}->{}".format(from_pid, self.pid)
        self.channel_marker_store[key] = set()
        return key
    
    def initiate_self_global_snapshot(self):
        new_marker = "{}.{}".format(self.pid, len(self.global_snap_store)+1)
        self.local_snap_store[new_marker] = None
        self.global_snap_store[new_marker] = None
        return new_marker
    
    def is_a_new_marker(self, marker_id):
        return marker_id not in self.local_snap_store
    
    # call this if is_a_new_marker returns true
    def track_new_marker(self, channel, marker_id):
        for channel in self.channel_marker_store:
            self.channel_marker_store[channel].add(marker_id)
        self.channel_marker_store[channel].remove(marker_id)
        self.active_markers.add(marker_id)
    
    # call after initiate_global_snapshot and track_new_marker
    def start_a_local_snap_store(self, marker_id, state):
        self.local_snap_store[marker_id] = LocalSnapshot(state)
        for channel in self.channel_marker_store:
            # makes sure empty transactions are feeded
            self.local_snap_store[channel] = list()
    
    # call this if is_a_new_marker returns false or for a token message
    def handle_incoming_channel_message(self, channel, message):
        if message.message_type == Consts.MARKER:
            self.channel_marker_store[channel].remove(message.marker_id)
            return self.get_completed_local_snap_store() # None / if any marker has completed the execution
        for marker_id in self.channel_marker_store[channel]:
            self.local_snap_store[marker_id].add_info(channel, message)
    
    def get_completed_local_snap_store(self):
        curr_markers = set()
        for channel in self.channel_marker_store:
            curr_markers.union(self.channel_marker_store[channel])
        completed_markers = self.active_markers.difference(curr_markers)
        # this is always going to be max 1 in our case
        completed_marker = list(completed_markers)[0] if len(completed_markers) else None
        self.active_markers.remove(completed_marker) if completed_marker else None
        return completed_marker
    
    # call this method when update_incoming_channel returns a marker
    def generate_message_for_snap_send(self, marker_id):
        client = marker_id.split(".")[0]
        # if the client is you, just update global store and send None
        if client == self.pid:
            self.global_snap_store[marker_id].add_info(self.pid, self.local_snap_store[marker_id])
            return client, None
        message = Message(Consts.SNAP, self.pid, client, data=self.local_snap_store[marker_id])
        return client, message

    # call this when someone sends you their local snap
    def update_global_snapshot(self, client, message):
        is_snap_complete = self.global_snap_store[message.marker_id].add_info(message.from_pid, message.data)
        # Once completed, just print the global snapshot
        if is_snap_complete:
            print(str(self.global_snap_store[message.marker_id]))