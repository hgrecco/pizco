# -*- coding: utf-8 -*-
"""
    pyzco.util
    ~~~~~~~~~~

    Useful functions.

    :copyright: 2013 by Hernan E. Grecco, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""


class Signal(object):
    """PyQt like signal object
    """
    def __init__(self):
        #add dummy types for signals or hide a pyqtSignal behind to resync with qt main loop
        self.slots = []

    def connect(self, slot):
        #add dummy connection type maybe this the place to create the pyqtSignals to be able to resync with qt event loop
        if slot not in self.slots:
            self.slots.append(slot)

    def disconnect(self, slot=None):
        if slot is None:
            self.slots = []
        else:
            self.slots.remove(slot)

    def emit(self, *args):
        #thread safety in qt main loop maybe pyqtSignals should be called behind
        for slot in self.slots:
            slot(*args)

def bind(sock, endpoint='tcp://127.0.0.1:0'):
    """Bind socket to endpoint accepting a variety of endpoint formats.

    If connection is tcp and port is 0 or not given, it will call bind_to_random_port.

    :param sock: Socket to bind
    :type sock: zmq.Socket
    :param endpoint: endpoint to bind as string or (address, port) tuple
    :type endpoint: tuple or str

    :return: bound endpoint
    :rtype: str
    """
    if not endpoint:
        endpoint = 'tcp://127.0.0.1:0'
    elif isinstance(endpoint, (tuple, list)):
        endpoint = 'tcp://{}:{}'.format(*endpoint)

    if endpoint.startswith('tcp://') and endpoint.endswith(':0'):
        endpoint = endpoint[:-2]
        port = sock.bind_to_random_port(endpoint)
        endpoint += ':' + str(port)
    else:
        sock.bind(endpoint)

    return endpoint
