"""
CPSC 5520, Seattle University
This is the client program lab1.py that sends JOIN message to GCD server on host cs2.seattleu.edu and port 23600.
Then it sends HELLO message to all the groups it received in response from the server.
:Authors: Fnu Shipra
:Version: 0.0
"""
from datetime import datetime
from email import message
from enum import Enum
from http import client
from select import select
import sys
import pickle
import socket
import socketserver
import selectors
import types

BUF_SZ = 1024                       # tcp receive buffer size
class State(Enum):
    """
    Enumeration of states a peer can be in for the Lab2 class.
    """
    QUIESCENT = 'QUIESCENT'  # Erase any memory of this peer

    # Outgoing message is pending
    SEND_ELECTION = 'ELECTION'
    SEND_VICTORY = 'COORDINATOR'
    SEND_OK = 'OK'

    # Incoming message is pending
    WAITING_FOR_OK = 'WAIT_OK'  # When I've sent them an ELECTION message
    WAITING_FOR_VICTOR = 'WHO IS THE WINNER?'  # This one only applies to myself
    WAITING_FOR_ANY_MESSAGE = 'WAITING'  # When I've done an accept on their connect to my server

    def is_incoming(self):
        """Categorization helper."""
        return self not in (State.SEND_ELECTION, State.SEND_VICTORY, State.SEND_OK)

class Lab2(object):
    
    def __init__(self, gcd_address, next_birthday, su_id, listener_port, selector):
        self.gcd_address = gcd_address
        self.gcd_host = gcd_address[0]
        self.gcd_port = int(gcd_address[1])
        self.next_birthday = next_birthday
        days_to_birthday = (self.next_birthday - datetime.now()).days
        self.su_id = int(su_id)
        self.current_pid = (days_to_birthday, self.su_id)
        self.listener_port = listener_port
        self.gcd_socket = None
        print("listener port is ", listener_port)
        print('pid: ' , self.current_pid)
        self.members = []
        self.members_dict = {}
        self.leader = False
        self.peer_timeout = 1.5
        self.selector = selector
        self.peers = []
        self.client_selector = selectors.DefaultSelector()
        self.current_state = State.SEND_ELECTION

    def send_and_receive_message(self, message, s):
            if message[0] == "JOIN":
                pickled_message = pickle.dumps(message)
                s.sendall(pickled_message)
                data = s.recv(1024)
                response = pickle.loads(data)
                return response
            if message == "ELECTION":
                pickled_message = pickle.dumps(message)
                s.sendall(pickled_message)
                data = s.recv(1024)
                response = pickle.loads(data)
                return response
    
    def connect_to_GCD(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.connect((self.gcd_host, self.gcd_port))
        return s

    def send_join_message(self, s):
        print(self.current_pid)
        message = ('JOIN', (self.current_pid, (self.gcd_host, self.listener_port)))
        return self.send_and_receive_message(message, s)

    def start_election(self):
        for member in self.members.items():
                client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                peer_pid = member[0][0]
                peerHost, peerPort = member[1]
                client_socket.settimeout(self.peer_timeout)
                if self.current_pid[0] < peer_pid or (self.current_pid[0] == peer_pid and self.current_pid[1] < member[0][1]):
                    try:
                        print("starting election with : ")
                        print("peer host" , peerHost)
                        print("peer port" ,peerPort)
                        client_socket.setblocking(False)
                        client_socket.connect_ex((peerHost, peerPort)) ## BLOCKING
                        events = selectors.EVENT_READ | selectors.EVENT_WRITE
                        self.selector.register(client_socket, events, data=self.handleElectionResponse)
                    except Exception as err:
                        print('failed to connect: {}', err)

    def set_state(self, member, state):
        print("received message in set state")
        print(state)

    def create_listening_socket(self, host, port):
        lsock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        lsock.bind((host, port))
        lsock.listen()
        print(f"Listening on {(host, port)}")
        lsock.setblocking(False)
        events = selectors.EVENT_READ
        self.selector.register(lsock, events, data=None)

    def accept_wrapper(self, sock):
        print("accept wrapper socket ")
        print(sock)
        conn, addr = sock.accept()  # Should be ready to read
        print(f"Accepted connection from {addr}")
        conn.setblocking(False)
        events = selectors.EVENT_READ | selectors.EVENT_WRITE
        # data = types.SimpleNamespace(addr=addr, inb=b"", outb=b"")
        self.selector.register(conn, events, data=self.service_connection) # WROTE FROM CLIENT SOCKET

    def handleElectionResponse(self, key, mask):
        print("called handle election response")
        sock = key.fileobj
        data = key.data
        if mask & selectors.EVENT_READ:
            recv_data = sock.recv(1024)  # Should be ready to read
            if recv_data:
                print("received response is ")
                print(recv_data)
            else:
                print(f"Closing connection to {data}")
                self.selector.unregister(sock)
                sock.close()
        if mask & selectors.EVENT_WRITE:
            print("inside write now fucking..")
            message = pickle.dumps(('ELECTION', self.members))
            if self.current_state == State.SEND_ELECTION:
                sock.send(message) 
                self.current_state = State.WAITING_FOR_OK
                
    def service_connection(self, key, mask):
        sock = key.fileobj
        data = key.data
        if mask & selectors.EVENT_READ:
            print("entered event read")
            print(sock)
            recv_data = sock.recv(1024)  # Should be ready to read
            if recv_data:
                client_message = pickle.loads(recv_data)
                self.members = client_message[1] # update members list
                print("updated members list with ")
                print(self.members)
            else:
                print(f"Closed connection")
                self.selector.unregister(sock)
                sock.close()
        if mask & selectors.EVENT_WRITE:
                sock.send(b'OK')
            
            
    def update_members_list(self, members):
        self.members = members
        for key in members:
            self.members_dict[key] = State.SEND_ELECTION

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
    lab2 = Lab2(sys.argv[1:3], next_bd, su_id, listener_port, sel)
    gcd_socket = lab2.connect_to_GCD()
    members = lab2.send_join_message(gcd_socket)
    print(members)
    lab2.update_members_list(members)
    lab2.create_listening_socket(sys.argv[1], listener_port)
    # send an election message
    lab2.start_election()
    try:
        while True:
            print("executing loop")
            events = lab2.selector.select(timeout=None) #this is a blocking call
            print(len(events))
            print(events)
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