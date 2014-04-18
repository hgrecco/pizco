# -*- coding: utf-8 -*-
"""
    pyzco.util
    ~~~~~~~~~~

    Useful functions.

    :copyright: 2013 by Hernan E. Grecco, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""
import inspect
import traceback
from zmq import ZMQError

class Signal(object):
    """PyQt like signal object
    """
    # TODO reflexion on thread safety and resync with qt main loop, like embedding a pyqtSignal in Signal
    # Especially in server part, where async operation are not well understood
    def __init__(self):
        self.slots = []

    def connect(self, slot):
        if slot not in self.slots:
            spec = inspect.getargspec(slot)
            self.slots.append(slot)

    def disconnect(self, slot=None):
        if slot is None:
            self.slots = []
        else:
            self.slots.remove(slot)

    def emit(self, *args):
        for slot in self.slots:
            #from functools import partial
            spec = inspect.getargspec(slot)
            #pcbk = partial(slot,*args)
            #print spec
            #print args
            #print slot
            #print type(slot)
            #print len(args)
            #print len(spec.args)
            if spec.varargs is None:
                if inspect.ismethod(slot):
                    if len(args) >= len(spec.args):
                        slot(*args[1:len(spec.args)])
                    else:
                        slot(*args[:len(spec.args)])
                else:
                    slot(*args[:len(spec.args)])
            else:
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
        try:
            sock.bind(endpoint)
        except Exception as e:
            from . import LOGGER
            import traceback
            LOGGER.error("connecting endpoint {} : ".format(endpoint))
            LOGGER.error(traceback.format_exc())
            raise e

    return endpoint
