# -*- coding: utf-8 -*-
"""
    pyzco.clientserver
    ~~~~~~~~~~~~~~~~~~

    Implements Client and Server agents.

    :copyright: 2013 by Hernan E. Grecco, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""


import os
import sys
import inspect
import threading
import traceback
from collections import defaultdict

from multiprocessing import Process, Manager
import multiprocessing as mp

from . import LOGGER
from .util import Signal
from .agent import Agent, default_io_loop
from .compat import futures

import logging
#logger = mp.log_to_stderr()
#logger.setLevel(mp.SUBDEBUG)

HIDE_TRACEBACK = os.environ.get('PZC_HIDE_TRACEBACK', True)
CREATION_TIMEOUT = os.environ.get('PZC_CREATION_TIMEOUT',2.5)

class RemoteAttribute(object):
    """Representing a remote attribute that can handle
     callables, container types, descriptors and signals.

    :param request: a callable used to send the request to the server, taking to arguments action and payload.
    :param name: name of the attribute.
    :param signal_manager:
    """

    def __init__(self, name, request, signal_manager):
        self.name = name
        self.request = request
        self.signal_manager = signal_manager

    def __get__(self, key):
        return self.request('exec', {'name': self.name,
                                     'method': '__get__',
                                     'args': (key, )})

    def __set__(self, key, value):
        return self.request('exec', {'name': self.name,
                                     'method': '__set__',
                                     'args': (key, value)})

    def __getitem__(self, key):
        return self.request('exec', {'name': self.name,
                                     'method': '__getitem__',
                                     'args': (key,)})

    def __setitem__(self, key, value):
        return self.request('exec', {'name': self.name,
                                     'method': '__setitem__',
                                     'args': (key, value)})

    def __call__(self, *args, **kwargs):
        payload = {'name': self.name, 'method': '__call__'}
        if args:
            payload['args'] = args
        if kwargs:
            payload['kwargs'] = kwargs

        return self.request('exec', payload)

    def connect(self, fun):
        LOGGER.debug('Connecting %s to %s', self.name, fun)
        self.signal_manager('connect', self.name, fun)

    def disconnect(self, fun=None):
        self.signal_manager('disconnect', self.name, fun)

    #def emit(self, value, old_value, other):
    #    self.signal_manager('emit', self.name, (value, old_value, other))

    def emit(self, *args, **kwargs):
        self.signal_manager('emit', self.name, (args, kwargs))


def PSMessage(action, options):
    """Builds a message
    """
    return 'PSMessage', action, options


def ServerLauncher(*args, **kwargs):
    import time
    final_rep_endpoint = kwargs.pop("final_rep_endpoint",[])
    s = Server(*args)
    final_rep_endpoint.append(s.rep_endpoint)
    time.sleep(5)
    s.serve_forever()
    
class Server(Agent):
    """Serves an object for remote access from a Proxy. A Server can serve a single object.

    :param served_object: object to be served.

    .. seealso:: :class:`.Agent`
    .. seealso:: :class:`.Proxy`
    """

    def __init__(self, served_object, rep_endpoint='tcp://127.0.0.1:0', pub_endpoint='tcp://127.0.0.1:0',
                 ctx=None, loop=None):
        try:
            LOGGER.debug("Server start")
            if rep_endpoint.find("*") != -1:
                pub_endpoint = pub_endpoint.replace("127.0.0.1", "*")
            self.served_object = served_object
            if served_object is None:
                self.did_instantiate = False
            self.signal_calls = {}
            super(Server, self).__init__(rep_endpoint, pub_endpoint, ctx, loop)
        except:
            import traceback
            LOGGER.error(traceback.format_exc())

    def on_request(self, sender, topic, content, msgid):
        """Handles Proxy Server communication, handling attribute access in served_object.

        Messages between proxy and server are handled using a tuple
        containing three elements: a string 'PSMessage', `action` and `options`.

        From Proxy to Server, valid actions are:

        - `exec`: execute a method from an attribute served object.
        - `getattr`: get an attribute from the served object.
        - `setattr`: set an attribute to the served object.
        - `get`: get an attribute from the served object, returning a remote object
                 when necessary.

        From Server to Proxy, valid action are:

        - `return`: return a value.
        - `remote`: return a RemoteAttribute object.
        - `raise`: raise an exception.


        """
        try:
            content_type, action, options = content
            if content_type != 'PSMessage':
                raise ValueError('Invalid content type %s' % content_type)
        except:
            return super(Server, self).on_request(
                sender, topic, content, msgid)

        try:
            if action == 'exec':
                attr = getattr(self.served_object, options['name'])
                meth = getattr(attr, options['method'])
                ret = meth(*options.get('args', ()),
                           **options.get('kwargs', {}))

            elif action == 'getattr':
                ret = getattr(self.served_object, options['name'])

            elif action == 'setattr':
                setattr(self.served_object, options['name'], options['value'])
                return PSMessage('return', None)

            elif action == 'get':
                attr = getattr(self.served_object, options['name'])
                if options.get('force_as_object', False) or self.force_as_object(attr):
                    ret = attr
                elif self.return_as_remote(attr):
                    return PSMessage('remote', None)
                else:
                    ret = attr

            elif action == 'inspect':
                return PSMessage('return', self.inspect())
            elif action == 'ping':
                return PSMessage('ping', None)
            elif action == 'instantiate':
                if self.served_object is not None:
                    return PSMessage('raise', (Exception('Cannot instantiate another object.'),
                                               ''))

                mod_name, class_name = options['class'].rsplit('.', 1)
                mod = __import__(mod_name, fromlist=[class_name])
                klass = getattr(mod, class_name)
                self.did_instantiate = True
                self.served_object = klass(*options['args'], **options['kwargs'])
                return PSMessage('return', None)
            else:
                ret = Exception('invalid message action %s', action)
                return PSMessage('raise', (ret, ''))

            if isinstance(ret, futures.Future):
                ret.add_done_callback(lambda fut: self.publish('__future__',
                                                               {'msgid': msgid,
                                                                'result': fut.result() if not fut.exception() else None,
                                                                'exception': fut.exception()}))
                return PSMessage('future_register', msgid)

            return PSMessage('return', ret)

        except Exception as ex:
            exc_type, exc_value, exc_tb = sys.exc_info()
            tb = traceback.format_exception(exc_type, exc_value, exc_tb)[1:]
            return PSMessage('raise', (ex, tb))

    #def emit(self, topic, value, old_value, other):
    #    LOGGER.debug('Emitting {}, {}, {}, {}'.format(topic, value, old_value, other))
    #    self.publish(topic, (value, old_value, other))

    def emit(self, topic, *args, **kwargs):
        if LOGGER.isEnabledFor(logging.DEBUG):
            LOGGER.debug('Emitting %s, %s, %s', topic, args, kwargs)
        self.publish(topic, (args, kwargs))

    def on_subscribe(self, topic, count):
        try:
            signal = getattr(self.served_object, topic)
        except AttributeError:
            return

        if count == 1:
            LOGGER.debug('Connecting %s signal on server', topic)
            #def fun(value, old_value=None, other=None):
            #    LOGGER.debug('ready to emit')
            #    self.emit(topic, value, old_value, other)

            def fun(*args, **kwargs):
                #LOGGER.debug('ready to emit')
                self.emit(topic, *args, **kwargs)

            #Signal emission on server with this closure.
            self.signal_calls[topic] = fun
            signal.connect(self.signal_calls[topic])

    def unsubscribe(self, rep_endpoint, topic, pub_endpoint=None):
        if self.remote_pub_endpoint.startswith("tcp://*"):
                defined_endpoint = self.remote_rep_endpoint.replace("/","").split(":")
                defined_endpoint[1] = "//*"
                rep_endpoint = ":".join(defined_endpoint)

        super(ProxyAgent,self).unsubscribe(rep_endpoint,topic,pub_endpoint)


    def on_unsubscribe(self, topic, count):
        try:
            signal = getattr(self.served_object, topic)
        except AttributeError:
            return
        if count == 0:
            LOGGER.debug('Disconnecting %s signal on server', topic)
            signal.disconnect(self.signal_calls[topic])
            del self.signal_calls[topic]
            
    @staticmethod
    def pick_free_port(bind_address):
        import socket
        """ Picks a free port """
        test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        bind_address = bind_address.replace("*","0.0.0.0")
        test_socket.bind((bind_address, 0))
        free_port = int(test_socket.getsockname()[1])
        test_socket.close()
        return free_port
        
    @classmethod
    def serve_in_thread(cls, served_cls, args, kwargs,
                        rep_endpoint='tcp://127.0.0.1:0', pub_endpoint='tcp://127.0.0.1:0'):

        final_rep_endpoint = []
        t = threading.Thread(target=ServerLauncher, args=(None, rep_endpoint, pub_endpoint),kwargs={"final_rep_endpoint":final_rep_endpoint})

        t.start()
        while not final_rep_endpoint:
            pass
        rep_endpoint = final_rep_endpoint[0]

        if rep_endpoint.find("*") != -1:
            pxy_endpoint = rep_endpoint.replace("*","127.0.0.1")
        else:
            pxy_endpoint = rep_endpoint

        proxy = Proxy(pxy_endpoint)
        proxy._proxy_agent.instantiate(served_cls, args, kwargs)
        proxy._proxy_inspection()

        return proxy



    @classmethod
    def serve_in_process(cls, served_cls, args, kwargs,
                         rep_endpoint, pub_endpoint='tcp://127.0.0.1:0',
                         daemon=True,
                         verbose=False, gui=False):

        manager = Manager()
        final_rep_endpoint = manager.list()
        p = Process(target=ServerLauncher, args=(None, rep_endpoint, pub_endpoint),kwargs={"final_rep_endpoint":final_rep_endpoint})
        p.daemon=daemon
        p.start()
        import time
        while not final_rep_endpoint:
            pass
        rep_endpoint = final_rep_endpoint[0]

        if rep_endpoint.find("*") != -1:
            pxy_endpoint = rep_endpoint.replace("*", "127.0.0.1")
        else:
            pxy_endpoint = rep_endpoint
        proxy = Proxy(pxy_endpoint)
        proxy._proxy_agent.instantiate(served_cls, args, kwargs)
        proxy._proxy_inspection()

        return proxy

    def serve_forever(self):
        self.join()
        LOGGER.debug('Server stopped {} {} '.format(self,self.rep_endpoint))

    def return_as_remote(self, attr):
        """Return True if the object must be returned as a RemoteAttribute.

        Override this function to customize your server.
        """
        return (hasattr(attr, '__get__') or
                hasattr(attr, '__getitem__') or
                hasattr(attr, '__setitem__') or
                callable(attr) or
                hasattr(attr, 'connect') and hasattr(attr, 'disconnect') and hasattr(attr, 'emit'))

    def is_signal(self, attr):
        return (hasattr(attr, 'connect') and hasattr(attr, 'disconnect') and
                hasattr(attr, 'emit') and hasattr(attr, '_nargs'))

    def force_as_object(self, attr):
        """Return True if the object must be returned as object even if it meets the conditions of a RemoteAttribute.

        Override this function to customize your server.
        """
        return False

    def inspect(self):
        """Inspect the served object and return a tuple containing::

        - a set with the attributes that should be returned as RemoteAttribute.
        - a set with the attributes that should be returned as Objects.

        Override this function to customize your server.
        .. seealso: return_as_remote, force_as_object
        """
        remotes = set([name for name, value in inspect.getmembers(self.served_object)
                       if not name.startswith('_') and self.return_as_remote(value)])
        objects = set([name for name, value in inspect.getmembers(self.served_object)
                       if not name.startswith('_') and self.force_as_object(value)])
        signals = set([name for name, value in inspect.getmembers(self.served_object)
                       if not name.startswith('_') and self.is_signal(value)])
        return remotes, objects, signals

    def __getstate__(self):
        return {"remote_rep_endpoint":self.rep_endpoint}

    def __setstate__(self, state):
        print("seting state")
        self.__class__ = Proxy
        self = Proxy.__init__(self,state["remote_rep_endpoint"])
        print("calling creation")

class SignalDict(defaultdict):
    #FIXME : Signal default dict. Signal Class Can Be Replaced to Another Type
    #FIXME : Pass the Type Of the Signal Dict Here
    def __init__(self, request, *args, **kwargs):
        defaultdict.__init__(self, Signal, *args, **kwargs)
        self._request = request

    def __missing__(self, key):
        # TODO ZMQError cannot be completed in current state
        args = []
        for k in ['_nargs', '_kwargs', '_varargs', '_varkwargs']:
            v = self._request('exec', {
                'name': key[1], 'method': '__getattribute__', 'args': (k, )})
            args.append(v)
        LOGGER.debug('Creating signal for %s with args %s', key, args)
        return Signal(*args)


class ProxyAgent(Agent):
    """Helper class that handles Proxy to Server communication.

    :param remote_rep_endpoint: REP endpoint of the Server.
    """

    def __init__(self, remote_rep_endpoint, creation_timeout=0):
        super(ProxyAgent, self).__init__()

        self._remote_stopping = threading.Event()
        self._remote_stopping.clear()

        self.remote_rep_endpoint = remote_rep_endpoint

        if creation_timeout:
            if self.ping_server(creation_timeout) != 'ping':
                super(ProxyAgent, self).__del__()
                raise Exception("Timeout")

        ret = self.request(self.remote_rep_endpoint, 'info')
        self.remote_pub_endpoint = ret['pub_endpoint']

        LOGGER.debug('Started Proxy pointing to REP: %s and PUB: %s',
                     self.remote_rep_endpoint, self.remote_pub_endpoint)

        #self._signals = defaultdict(Signal)
        self._signals = SignalDict(self.request_server)
        #: Maps msgid to future object.
        self._futures = {}
        #: Subscribe to notifications when a future is finished.
        self.subscribe(self.remote_rep_endpoint, '__future__',
                       self.on_future_completed, self.remote_pub_endpoint)

        self.subscribe(self.remote_rep_endpoint, '__status__',
                       self.on_status_changed, self.remote_pub_endpoint)

        #FIXME subscribe to server end signal

    def inspection(self):
        self._proxy_attr_as_remote, self._proxy_attr_as_object, self._proxy_signals = self.request_server('inspect', {})
        # TODO build signals here
        for k in self._proxy_signals:
            remote_endpoint = self.remote_rep_endpoint
            pub_endpoint = self.remote_pub_endpoint
            if pub_endpoint.find("*") != -1:
                signal_endpoint = "tcp://*:"+remote_endpoint.split(":")[-1]
            else:
                signal_endpoint = remote_endpoint
            self._signals[(signal_endpoint, k)] = \
                self._signals[(signal_endpoint, k)]
        return self._proxy_attr_as_remote, self._proxy_attr_as_object, self._proxy_signals

    def ping_server(self,timeout=5000):
        return self.request_polled(self.remote_rep_endpoint, "ping", timeout)

    def request_server(self, action, options, force_as_object=False):
        """Sends a request to the associated server using PSMessage

        :param action: action to be sent.
        :param options: options of the action.
        :return:
        """
        if force_as_object:
            options['force_as_object'] = True

        content = self.request(self.remote_rep_endpoint, PSMessage(action, options))

        try:
            ret_type, ret_action, ret_options = content
            if ret_type != 'PSMessage':
                raise ValueError
        except:
            raise ValueError('Invalid response from Server {0}'.format(content))

        if ret_action == 'raise':
            exc, traceback_text = ret_options
            exc._pzc_traceback = traceback_text
            raise exc

        elif ret_action == 'remote':
            return RemoteAttribute(options['name'], self.request_server, self.signal_manager)

        elif ret_action == 'return':
            return ret_options

        elif ret_action == 'future_register':
            fut = futures.Future()
            fut.set_running_or_notify_cancel()
            self._futures[ret_options] = fut
            return fut
        else:
            raise ValueError('Unknown {0}'.format(ret_action))

    def signal_manager(self, action, signal_name, fun):

        #the remote rep endpoint is ignored in the server sending with it is not possible on multiple threads
        #TODO : check if its compliant to multiple object
        #fixing connection with wildcard adresses
        #LOGGER.debug(("signal_manager",action,signal_name,fun))
        #LOGGER.debug(("signal_manager",self._signals))


        if self.remote_pub_endpoint.find("*") != -1:
            defined_endpoint = self.remote_rep_endpoint.replace("/", "").split(":")
            defined_endpoint[1] = "//*"
            signal_endpoint = ":".join(defined_endpoint)
        else:
            signal_endpoint = self.remote_rep_endpoint

        if action == 'connect':
            if not self._signals[(signal_endpoint, signal_name)].slots:
                self.subscribe(self.remote_rep_endpoint, signal_name, None, self.remote_pub_endpoint)
            self._signals[(signal_endpoint, signal_name)].connect(fun)

        elif action == 'disconnect':
            self._signals[(signal_endpoint, signal_name)].disconnect(fun)
            if not self._signals[(signal_endpoint, signal_name)].slots:
                self.unsubscribe(self.remote_rep_endpoint, signal_name, self.remote_pub_endpoint)

        elif action == 'emit':
            #TODO: Emit signal in the server!
            pass
        else:
            raise ValueError(action)

    def on_status_changed(self,sender,topic,content,msgid):
        if content == 'stop':
            self._remote_stopping.set()

    def server_stopped(self):
        return self._remote_stopping.isSet()

    def wait_server_stop(self,timeout=None):
        return self._remote_stopping.wait(timeout)
                        
    def on_future_completed(self, sender, topic, content, msgid):
        try:
            fut = self._futures[content['msgid']]
            if content['exception']:
                fut.set_exception(content['exception'])
            else:
                fut.set_result(content['result'])
        except KeyError:
            LOGGER.debug("received unregistered future event {0} / {1}".format(content["msgid"],self._futures.keys))

    def on_notification(self, sender, topic, content, msgid):
        try:
            if (str(sender),str(topic)) in self._signals:
                self._signals[(sender, topic)].emit(*content[0], **content[1])
                #self._signals[(sender, topic)].emit(*content)
            else:
                LOGGER.error("Signal receive does not match _signals list retrieved from server : ERROR in signal list/ERROR in signal received")
                raise KeyError
        except KeyError:
            super(ProxyAgent, self).on_notification(
                sender, topic, content, msgid)

    def instantiate(self, served_cls, args, kwargs):
        LOGGER.debug("instanciate class")
        if not isinstance(served_cls, str):
            served_cls = served_cls.__module__ + '.' + served_cls.__name__
        self.request_server('instantiate', {'class': served_cls, 'args': args, 'kwargs': kwargs})


def _except_hook(type, value, tb):
    for item in traceback.format_exception(type, value, tb)[:-1] + getattr(value, '_pzc_traceback', []):
        if HIDE_TRACEBACK and 'pizco.py' in item:
            continue
        sys.stderr.write(item)


def set_excepthook():
    sys.excepthook = _except_hook


import socket
def check_port_opened(ip,port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex((ip,port))
    if result == 0:
       return True
    else:
       sock.close()
       del sock
       return False

def endpoint_to_connection(endpoint):
    edp = endpoint.split(":")
    ip = edp[1].replace("/","")
    port = int(edp[-1])
    return ip,port

class Proxy(object):
    """Proxy object to access a server.

    :param remote_endpoint: endpoint of the server.
    """
    def __init__(self, remote_endpoint,creation_timeout=0, ):
        self._proxy_agent = ProxyAgent(remote_endpoint, creation_timeout)
        self._proxy_attr_as_remote = []
        self._proxy_attr_as_object = []
        self._proxy_signals = {}
        self._proxy_inspection()

    def __getattr__(self, item):

        if item.startswith('_proxy_'):
            return super(Proxy,self).__getattr__(item)

        if self._proxy_agent.server_stopped():
            raise Exception("Server Stopped!!!")

        if item in self._proxy_attr_as_remote:
            return RemoteAttribute(item, self._proxy_agent.request_server, self._proxy_agent.signal_manager)

        return self._proxy_agent.request_server('get', {'name': item}, item in self._proxy_attr_as_object)

    def __setattr__(self, item, value):
        if item.startswith('_proxy_'):
            super(Proxy, self).__setattr__(item, value)
            return
        if self._proxy_agent.server_stopped():
            raise Exception("Server Stopped!!!")
        return self._proxy_agent.request_server('setattr', {'name': item, 'value': value})

    def _proxy_ping(self,ping_timeout=3000):
        return self._proxy_agent.ping_server(ping_timeout)

    def _proxy_started(self):
        return self._proxy_agent.started()

    def _proxy_wait_start(self,timeout=3):
        return self._proxy_agent.wait_start(timeout)

    def _proxy_stopped(self):
        return self._proxy_agent.stopped()

    def _proxy_wait_stop(self,timeout=5):
        return self._proxy_agent.wait_stop(timeout)

    def _proxy_stop_server(self, timeout=5):
        self._proxy_agent.request(self._proxy_agent.remote_rep_endpoint, 'stop')
        self._proxy_agent.wait_server_stop(timeout=5)
        while check_port_opened(*endpoint_to_connection(self._proxy_agent.remote_rep_endpoint)):
            import time
            time.sleep(0.5)


    def _proxy_rep_endpoint(self):
        return self._proxy_agent.remote_rep_endpoint
        
    def _proxy_stop_me(self):
        self._proxy_agent.stop()
        self._proxy_wait_stop()

    def _proxy_inspection(self):
        self._proxy_attr_as_remote, self._proxy_attr_as_object, self._proxy_signals = self._proxy_agent.inspection()

    def __del__(self):
        if hasattr(super(Proxy, self), "_proxy_agent"):
            self._proxy_agent.stop()
            self._proxy_wait_stop()

    def __getstate__(self):
        return {"remote_rep_endpoint":self._proxy_agent.remote_rep_endpoint}

    def __setstate__(self, state):
        Proxy.__init__(self,state["remote_rep_endpoint"])