"""
CPSC 5520, Seattle University
This is the lab2.py that implements the Bully algorithm in Python. 
It performs election in order to find the leader/ coordinator in the group of members/ peers.
Once the leader is found, the algorithm ends.
:Authors: Fnu Shipra
:Version: 0.0
"""
from datetime import datetime
from enum import Enum
import sys
import pickle
import socket
import selectors

BUF_SZ = 1024                                   # tcp receive buffer size
"""
State class
"""
class State(Enum):
    """
    Enumeration of states a peer can be in for the Lab2 class.
    """

    # Outgoing message is pending
    SEND_ELECTION = 'ELECTION'
    SEND_VICTORY = 'COORDINATOR'
    SEND_OK = 'OK'

    # Incoming message is pending
    WAITING_FOR_OK = 'WAIT_OK'  # When I've sent them an ELECTION message
    WAITING_FOR_VICTOR = 'WHO IS THE WINNER?'  # This one only applies to myself
    WAITING_FOR_ANY_MESSAGE = 'WAITING'  # When I've done an accept on their connect to my server
    ELECTION_NOT_IN_PROGRESS = 'ELECTION_NOT_IN_PROGRESS'
    ELECTION_IN_PROGRESS = 'ELECTION_IN_PROGRESS'
    LEADER = 'LEADER'
    LEADER_FOUND = 'LEADER_FOUND'

    def is_incoming(self):
        """Categorization helper."""
        return self not in (State.SEND_ELECTION, State.SEND_VICTORY, State.SEND_OK)

"""
Lab2 class
"""
class Lab2(object):
    
    """
    The constructor/ init method which takes parameters - gcd_address, birthday, su_id, and listener port
    """
    def __init__(self, gcd_address, next_birthday, su_id, listener_port):
        self.gcd_address = gcd_address
        self.gcd_host = gcd_address[0]
        self.gcd_port = int(gcd_address[1])
        self.next_birthday = next_birthday
        days_to_birthday = (self.next_birthday - datetime.now()).days
        self.su_id = int(su_id)
        self.current_pid = (days_to_birthday, self.su_id)
        self.current_election_data = ""
        self.listener_port = listener_port
        self.gcd_socket = None
        print("listener port is ", listener_port)
        print('pid: ' , self.current_pid)
        self.members = []
        self.members_dict = {}
        self.leader = False
        self.peer_timeout = 1.5
        self.selector = selectors.DefaultSelector()
        self.peers = []
        self.current_state = State.SEND_ELECTION

    """
    The method pickles the message and sends to the server if it gets JOIN message. 
    Then it recieves the message, unpickles it and and send back the response
    """
    def send_and_receive_message(self, message, s):
        if message[0] == "JOIN":
            pickled_message = pickle.dumps(message)
            s.sendall(pickled_message)
            data = s.recv(1024)
            response = pickle.loads(data)
            return response
    
    """
    The method is used to make the connection to GCD server and returns the socket
    """
    def connect_to_GCD(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((self.gcd_host, self.gcd_port))
        return s

    """
    This method sends the JOIN message along with process id and listener address to send_and_receive_message
    """
    def send_join_message(self, s):
        print(self.current_pid)
        self.current_state = State.SEND_ELECTION
        message = ('JOIN', (self.current_pid, (self.gcd_host, self.listener_port)))
        return self.send_and_receive_message(message, s)

    """
    This method is to start the election within the group and handles the messages received back in response from the peer
    and updates the members states accordingly.
    """
    def start_election(self):
        hasReceivedOk = False
        self.current_state = State.WAITING_FOR_OK
        print("starting election with the group")
        for member in self.members.items(): 
            peer_pid = member[0][0]
            peerHost, peerPort = member[1]
            if peer_pid == self.current_pid[0]:
                self.members_dict[self.current_pid] = self.current_state
                continue
            else:
                self.members_dict[member[0]] = State.ELECTION_IN_PROGRESS               # Update all others states to election in progress
        for member in self.members.items():
                peer_pid = member[0][0]
                peerHost, peerPort = member[1]
                if peer_pid == self.current_pid[0]:
                    continue
                try:
                    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    client_socket.settimeout(self.peer_timeout)
                    print("peer host" , peerHost)
                    print("peer port" ,peerPort)
                    client_socket.connect((peerHost, peerPort))
                    client_socket.sendall(pickle.dumps((State.SEND_ELECTION, self.members, self.current_pid)))
                    msg = pickle.loads(client_socket.recv(1024))
                    if msg == "OK":
                        print("Received OK")
                        hasReceivedOk = True
                        self.members_dict[member[0]] = State.WAITING_FOR_VICTOR
                except socket.timeout:               
                    self.members_dict[member[0]] = State.WAITING_FOR_VICTOR
                except Exception as err:
                    print('failed to connect: {}', err)
        if hasReceivedOk:                                                               # After receiving OK, now waiting for a leader in the group
            self.members_dict[self.current_pid] = State.WAITING_FOR_VICTOR
            print(self.members_dict)
        else:
            print("Sending Coordinate message to everyone as I am the leader... ")
            self.current_state = State.SEND_VICTORY
            self.send_coordinator_message()
            self.members_dict[self.current_pid] = self.current_state

    """
    This method sends the Coordinate message to everyone in the group 
    after winning the election. It also prints the current state of the group.
    """
    def send_coordinator_message(self):
        for member in self.members.items():
            peer_pid = member[0][0]
            peerHost, peerPort = member[1]
            if peer_pid == self.current_pid[0]:
                self.current_state = State.LEADER
                self.members_dict[member[0]] = State.LEADER
                continue
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.settimeout(self.peer_timeout)
            print("sending coordinator message to :  ")
            print("peer host" , peerHost)
            print("peer port" ,peerPort)
            client_socket.connect((peerHost, peerPort))
            client_socket.sendall(pickle.dumps((State.SEND_VICTORY, self.members, self.current_pid)))
            self.members_dict[member[0]] = State.LEADER_FOUND
        print("Current state of the group")
        print(self.members_dict)

    """
    This method creates the listening socket that listens to whatever message it receives from the peer
    so it invokes the read event and register the event in the selector to make it non blocking.
    """
    def create_listening_socket(self, host, port):
        lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lsock.bind((host, port))
        lsock.listen()
        print(f"Listening on {(host, port)}")
        lsock.setblocking(False)
        events = selectors.EVENT_READ
        self.selector.register(lsock, events, data=None)

    """
    This method accepts the socket connection for read and write events and
    register the events in the selector to make it non blocking.
    """
    def accept_wrapper(self, sock):
        print("accept wrapper socket ")
        print(sock)
        conn, addr = sock.accept()                                          # Should be ready to read
        print(f"Accepted connection from {addr}")
        conn.setblocking(False)
        events = selectors.EVENT_READ | selectors.EVENT_WRITE
        self.selector.register(conn, events, data=self.service_connection) # Wrote from client socket
                
    """
    This method is the service connection method which is a server that sends the messages to client 
    and updates the states of all the members in the group.
    """
    def service_connection(self, key, mask):
        sock = key.fileobj
        data = key.data
        if mask & selectors.EVENT_READ:                                     # Event read
            recv_data = sock.recv(1024)                                     # Should be ready to read
            if recv_data:
                client_message = pickle.loads(recv_data)
                if client_message[0] == State.SEND_ELECTION :
                    self.current_election_data  = client_message
                    self.members = client_message[1]                        
                    for member in self.members:                             # Update members list
                        self.members_dict[member] = State.ELECTION_IN_PROGRESS
                if client_message[0] == State.SEND_VICTORY:
                    self.current_election_data = client_message
                    self.current_state = State.ELECTION_NOT_IN_PROGRESS
                    print("We have a leader")
                    self.members  = client_message[1]
                    for member in self.members_dict:
                        if member == self.current_election_data[2]:
                            self.members_dict[member] = State.LEADER
                        else:
                            self.members_dict[member] = State.LEADER_FOUND
                    print("current state of the group")
                    print(self.members_dict)      
            else:
                print(f"Closed connection")                                 # Closing connection and unregistering the socket from the selector
                self.selector.unregister(sock)
                sock.close()
        if mask & selectors.EVENT_WRITE:                                    # Event write
            if self.current_election_data is not None:
                client_pid = self.current_election_data[2]
                print(self.current_pid)
                print(client_pid)
                if self.current_pid[0] > client_pid[0] or (self.current_pid[0] == client_pid[0] and self.su_id > client_pid[1]):
                    print("send ok to client")
                    sock.sendall(pickle.dumps('OK'))
                    print("Member state at the end of election")              # Printing state of the peers
                    print(self.members_dict)
                    for member in self.members:
                        if member[0] == self.current_pid[0] and self.current_state == State.LEADER:
                            self.members_dict[member] = State.LEADER
                            continue
                        else:
                            self.members_dict[member] = State.LEADER_FOUND
                    if self.current_state == State.LEADER:
                        self.send_coordinator_message()
            self.current_election_data  = None

    """
    This method updates the members list in member dictionary and updates the states.
    """      
    def update_members_list(self, members):
        self.members = members
        for key in members:
            self.members_dict[key] = State.SEND_ELECTION

"""
Main method of the program
"""
if __name__ == '__main__':
    if not 4 <= len(sys.argv) <= 6:
        print("Usage: python3 lab2.py GCDHOST GCDPORT SUID [DOB]")
        exit(1)
    if len(sys.argv) == 6:
        pieces = sys.argv[4].split('-')
        now = datetime.now()
        next_bd = datetime(now.year, int(pieces[1]), int(pieces[2]))
        if next_bd < now:
            next_bd = datetime(next_bd.year +1, next_bd.month, next_bd.day)
    else:
        next_bd = datetime(2023, 1, 1)

    print('Next Birthday: ', next_bd)
    su_id = int(sys.argv[3])
    print('SeattleU ID: ', su_id)
    listener_port = int(sys.argv[5])
    sel = selectors.DefaultSelector()
    lab2 = Lab2(sys.argv[1:3], next_bd, su_id, listener_port)               # Created lab2 object of Lab2 class
    gcd_socket = lab2.connect_to_GCD()                                      # Call to connect_to_GCD() method
    members = lab2.send_join_message(gcd_socket)                            # Call to send_join_message() method
    print(members)
    lab2.update_members_list(members)                                       # Call to update_members_list() method
    lab2.create_listening_socket(sys.argv[1], listener_port)                # Call to create_listening_socket() method        
    lab2.start_election()                                                   # Call to start_election() method
    try:
        while True:
            events = lab2.selector.select(timeout = None)                   # This is a blocking call
            for key, mask in events:
                if key.data is None:
                    lab2.accept_wrapper(key.fileobj)
                else:
                    callback = key.data
                    callback(key, mask)
    except KeyboardInterrupt:
        print("Caught keyboard interrupt, exiting")
    finally:
        lab2.selector.close()
