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
    if prob>0 and random.randint(0, 100)<prob*100:
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
    
    def __init__(self, state, channel):
        self.state = state
        self.channel_data = {}
        self.channel_data[channel] = {}

    def add_info(self, channel, message):
        if channel in self.channel_data:
            self.channel_data[channel].append(message)
        else:
            self.channel_data[channel] = [message];

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
            channel_data[channel] += data
        if len(self.client_data)==CLIENT_COUNT:
            update_complete = True
        return update_complete
    
    def __str__(self):
        output = "Marker ID - {}\n".format(self.marker_id)
        output += "Client Store - \n"
        output += "\n".join(["{} : {}".format(key, val) for key,val in client_data.items()])
        output += "\nChannel Store - \n"
        output += "\n".join(["{} : {}".format(key, ", ".join([str(x) for x in val])) for key,val in channel_data.items()])
        return output

class ClientStore:
    
    def __init__(self, pid):
        self.pid = pid
        self.channel_marker_store = dict()
        self.connection_store = dict()
        # key marker_id, value GlobalSnapshot
        self.global_snap_store = dict()
        # key marker_id, value LocalSnapshot
        self.local_snap_store = dict()
        self.active_markers = set()
    
    def add_incoming_connection(self, from_pid, connection_obj):
        # add the entry to marker store so that client track which marker data to track from that channel
        # this gives something like B->A
        key = "{}->{}".format(from_pid, self.pid)
        self.channel_marker_store[key] = set()
        self.connection_store[key] = connection_obj
        return key
    
    def initiate_global_snapshot(self):
        new_marker = "{}.{}".format(self.pid, len(self.global_snap_store)+1)
        self.local_snap_store[new_marker] = None
        self.global_snap_store[new_marker] = None
        return new_marker
    
    def track_marker(self, channel, marker_id):
        self.local_snap_store[marker_id] = None
        for channel in self.channel_marker_store:
            self.channel_marker_store[channel].add(marker_id)
        self.channel_marker_store[channel].remove(marker_id)
        self.active_markers.add(marker_id)
    
    def update_marker_data(self, channel, message):
        for marker_id in self.channel_marker_store[channel]:
            self.local_snap_store[marker_id].add_info(channel, message)
        return self.get_completed_local_snap_store()
    
    def get_completed_local_snap_store(self):
        curr_markers = set()
        for channel in self.channel_marker_store:
            curr_markers.union(self.channel_marker_store[channel])
        completed_markers = self.active_markers.difference(curr_markers)
        # this is always going to be max 1 in our case
        completed_marker = list(completed_markers)[0] if len(completed_markers) else None
        self.active_markers.remove(completed_marker) if completed_marker else None
        return completed_marker
    
    def generate_message_for_snap_send(self, marker_id):
        client = marker_id.split("->")[0]
        if client == self.pid:
            self.global_snap_store[marker_id].add_info(self.pid, self.local_snap_store[marker_id])
            return None
        message = Message(Consts.SNAP, self.pid, client, data=self.local_snap_store[marker_id])
        return client, message           