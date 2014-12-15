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
import types

class SignalError(Exception):
    pass


def specable(f):
    try:
        inspect.getargspec(f)
        return True
    except:
        return False

def spec_builtin(obj):
   """ Describe a builtin function """
   # Built-in functions cannot be inspected by
   # inspect.getargspec. We have to try and parse
   # the __doc__ attribute of the function.

   docstr = obj.__doc__
   args = ''

   if not docstr:
      if isinstance(obj,types.BuiltinFunctionType):
          docstr = obj.__name__+"(*args, **kwargs)"
      if isinstance(obj,types.BuiltinMethodType):
          docstr = obj.__name__+"(self, *args, **kwargs)"
    
   items = docstr.split('\n')
   if items:
      func_descr = items[0]
      s = func_descr.replace(obj.__name__,'')
      idx1 = s.find('(')
      idx2 = s.find(')',idx1)
      if idx1 != -1 and idx2 != -1 and (idx2>idx1+1):
         args = s[idx1+1:idx2]
         _varargs = False
         if "*args" in args:
             _varargs = True
         _kwvarargs = False
         if "**kwargs" in args:
             _kwvarargs = True
         return inspect.ArgSpec(
             args.split(" "), _varargs, _kwvarargs, [])
   
   if args=='':
        return inspect.ArgSpec(
                [], None, None, [])

def getspec(f):
    if specable(f):
        spec = inspect.getargspec(f)
        defaults = []
        if spec.defaults is not None:
            defaults = spec.defaults
        if inspect.ismethod(f) and spec.args[0]=="self":
            args = spec.args[1:]  # remove reference to self
        else:
            args = spec.args
        return inspect.ArgSpec(
            args, spec.varargs is not None,
            spec.keywords is not None, defaults)

    if hasattr(f, '__call__') and specable(f.__call__):
        spec = getspec(f.__call__)
        args = spec.args[1:]  # remove reference to self
        return inspect.ArgSpec(
            args, spec.varargs, spec.keywords, spec.defaults)

    if isinstance(f,types.BuiltinFunctionType):
        return spec_builtin(f)

    if isinstance(f,types.BuiltinMethodType):
        return spec_builtin(f)

    # TODO handle partials
    raise ValueError(
        "getspec doesn't know how to get function spec from type {0}".format(
            type(f)))


class Signal(object):
    """PyQt like signal object
    """

    def __init__(self, nargs=0, kwargs=None, varargs=False, varkwargs=False):
        # add dummy types for signals or hide a pyqtSignal behind to resync
        # with qt main loop
        self.slots = []
        self._nargs = nargs
        if kwargs is None:
            self._kwargs = []
        else:
            self._kwargs = kwargs
        self._varargs = varargs
        self._varkwargs = varkwargs

    @staticmethod
    def Auto():
        return Signal(nargs=-1)

    def _auto_match(self, nargs, kwargs = []):
        #autoconnect on first connection
        self._nargs = nargs
        self._kwargs = kwargs

    def _verify_slot(self, slot):
        # signal varags -> slot varargs
        # signal args -> slot args (or varargs)
        # signal kwargs -> slot kwargs
        
        if self._nargs == -1:
            autodetect = True
        else:
            autodetect = False

            
        spec = getspec(slot)
        if not spec.varargs:  # function expects args
            if self._varargs:
                raise SignalError(
                    "Slot {0} does not accept varargs".format(slot))
            else:  # check nargs
                if autodetect == True:
                    return
                    
                maxargs = len(spec.args)
                if maxargs < self._nargs:
                    raise SignalError(
                        "Slot {0} does not accept enough args {1} {2}".format(
                            slot, maxargs, spec))
                minargs = maxargs - len(spec.defaults)
                if minargs > self._nargs:
                    raise SignalError(
                        "Slot {0} expects too many args {1} {2}".format(
                            slot, minargs, spec))

        if not spec.keywords:  # function only accepts specific kwargs
            if self._varkwargs:
                raise SignalError(
                    "Slot {0} does not accept varkwargs".format(slot))
            else:  # signal only passes specific kwargs
                kwargs = spec.args[::-1][:len(spec.defaults)]

                if autodetect == True:
                    return

                
                for kw in self._kwargs:
                    if kw not in kwargs:
                        raise SignalError(
                            "Slot {0} does not accept keyword {1}".format(
                                slot, kw))

                
    def connect(self, slot):
        # add dummy connection type maybe this the place to create the
        # pyqtSignals to be able to resync with qt event loop
        if slot not in self.slots:
            # verify that this slot works
            self._verify_slot(slot)
            self.slots.append(slot)

    def disconnect(self, slot=None):
        if slot is None:
            self.slots = []
        else:
            self.slots.remove(slot)

    def _verify_emit(self, args, kwargs):

        if self._nargs == -1:
            self._auto_match(len(args),kwargs.keys())

        if not self._varargs:  # check args
            if (len(args)) != self._nargs:
                raise SignalError(
                    "emit called with invalid number of args {0} / {1}".format(
                        len(args), self._nargs))
                     
        if not self._varkwargs:  # check kwargs
            for k in kwargs:
                if k not in self._kwargs:
                    raise SignalError(
                        "emit called with invalid kwarg {0}".format(
                            k))

    def emit(self, *args, **kwargs):
        # thread safety in qt main loop maybe pyqtSignals should be
        # called behind

        self._verify_emit(args, kwargs)
        for slot in self.slots:
            slot(*args, **kwargs)


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
        endpoint = 'tcp://{0}:{1}'.format(*endpoint)

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
            LOGGER.error('connecting endpoint %s:\n%s', endpoint, traceback.format_exc())
            raise e

    return endpoint
