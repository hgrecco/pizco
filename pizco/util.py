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

def specable(f):
    try:
        inspect.getargspec(f)
        return True
    except:
        return False


def getspec(f):
    if specable(f):
        spec = inspect.getargspec(f)
        defaults = []
        if spec.defaults is not None:
            defaults = spec.defaults
        if inspect.ismethod(f) and spec.args[0]=="self":
            args = spec.args[1:]  # remove reference to self
        return inspect.ArgSpec(
            spec.args, spec.varargs is not None,
            spec.keywords is not None, defaults)
    if hasattr(f, '__call__') and specable(f.__call__):
        spec = getspec(f.__call__)
        args = spec.args[1:]  # remove reference to self
        return inspect.ArgSpec(
            args, spec.varargs, spec.keywords, spec.defaults)
    # TODO handle partials
    raise ValueError(
        "getspec doesn't know how to get function spec from type {}".format(
            type(f)))


class Signal(object):
    """PyQt like signal object
    """
    # TODO reflexion on thread safety and resync with qt main loop, like embedding a pyqtSignal in Signal
    # Especially in server part, where async operation are not well understood
    def __init__(self):
        self.slots = []

    def connect(self, slot):
        if slot not in self.slots:
            self.slots.append(slot)

    def disconnect(self, slot=None):
        if slot is None:
            self.slots = []
        else:
            self.slots.remove(slot)

            
    def emit(self, *args):
        try:
            for slot in self.slots:
                spec = getspec(slot)
                if not spec.varargs:
                    if inspect.ismethod(slot):
                        if len(args) >= len(spec.args):
                            slot(*args[1:len(spec.args)])
                        else:
                            slot(*args[:len(spec.args)])
                    else:
                        slot(*args[:len(spec.args)])
                else:
                    slot(*args)
        except:
            
            import traceback
            traceback.print_exc()
            print spec



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
