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

from multiprocessing import Process
import multiprocessing as mp

from . import LOGGER
from .util import Signal
from .agent import Agent
from .compat import futures

logger = mp.log_to_stderr()
logger.setLevel(mp.SUBDEBUG)


HIDE_TRACEBACK = os.environ.get('PZC_HIDE_TRACEBACK', True)


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

    def disconnect(self, fun):
        self.signal_manager('disconnect', self.name, fun)

    #def emit(self, value, old_value, other):
    #    self.signal_manager('emit', self.name, (value, old_value, other))

    def emit(self, *args, **kwargs):
        self.signal_manager('emit', self.name, (args, kwargs))


def PSMessage(action, options):
    """Builds a message
    """
    return 'PSMessage', action, options


def ServerLauncher(*args):
    import time
    s = Server(*args)
    #while not s._running:
    #    time.sleep(0.2)
    #while s._running:
    #    time.sleep(0.2)
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
            LOGGER.debug("test server")
            if rep_endpoint.find("*") != -1:
                pub_endpoint = pub_endpoint.replace("127.0.0.1", "*")
            self.served_object = served_object
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
            self.signal_calls[topic] = fun
            signal.connect(self.signal_calls[topic])

    def on_unsubscribe(self, topic, count):
        try:
            signal = getattr(self.served_object, topic)
        except AttributeError:
            return
        if count == 0:
            LOGGER.debug('Disconnecting %s signal on server', topic)
            signal.disconnect(self.signal_calls[topic])
            del self.signal_calls[topic]

    @classmethod
    def serve_in_thread(cls, served_cls, args, kwargs,
                        rep_endpoint, pub_endpoint='tcp://127.0.0.1:0'):
        t = threading.Thread(target=cls, args=(None, rep_endpoint, pub_endpoint))
        t.start()
        import time
        time.sleep(1)
        if rep_endpoint.find("*") != -1:
            pxy_endpoint = rep_endpoint.replace("*","127.0.0.1")
        else:
            pxy_endpoint = rep_endpoint
        proxy = Proxy(pxy_endpoint)
        proxy._proxy_agent.instantiate(served_cls, args, kwargs)
        return proxy

    @classmethod
    def serve_in_process(cls, served_cls, args, kwargs,
                         rep_endpoint, pub_endpoint='tcp://127.0.0.1:0',
                         verbose=False, gui=False):
        #cwd = os.path.dirname(inspect.getfile(served_cls))
        #launch(cwd, rep_endpoint, pub_endpoint, verbose, gui)
        #mp.set_start_method("forkserver")
        p = Process(target=ServerLauncher, args=(None, rep_endpoint, pub_endpoint))
        p.daemon=True
        p.start()
        import time
        time.sleep(1)
        if rep_endpoint.find("*") != -1:
            pxy_endpoint = rep_endpoint.replace("*", "127.0.0.1")
        else:
            pxy_endpoint = rep_endpoint
        proxy = Proxy(pxy_endpoint)
        proxy._proxy_agent.instantiate(served_cls, args, kwargs)
        return proxy

    def serve_forever(self):
        self.join()
        LOGGER.debug('Server stopped')

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


class SignalDict(defaultdict):
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

        self.remote_rep_endpoint = remote_rep_endpoint

        if creation_timeout:
            if self.ping_server(creation_timeout) != 'ping':
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
                        
    def on_future_completed(self, sender, topic, content, msgid):
        fut = self._futures[content['msgid']]
        if content['exception']:
            fut.set_exception(content['exception'])
        else:
            fut.set_result(content['result'])

    def on_notification(self, sender, topic, content, msgid):
        try:
            if (sender,topic) in self._signals:
                self._signals[(sender, topic)].emit(*content[0], **content[1])
                #self._signals[(sender, topic)].emit(*content)
            else:
                LOGGER.warning("not supposed to happen")
                raise KeyError
        except KeyError:
            super(ProxyAgent, self).on_notification(
                sender, topic, content, msgid)

    def instantiate(self, served_cls, args, kwargs):
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


class Proxy(object):
    """Proxy object to access a server.

    :param remote_endpoint: endpoint of the server.
    """
    def __init__(self, remote_endpoint,creation_timeout=0):
        self._proxy_agent = ProxyAgent(remote_endpoint, creation_timeout)
        self._proxy_attr_as_remote, self._proxy_attr_as_object, self._proxy_signals = self._proxy_agent.request_server('inspect', {})
        # TODO build signals here
        for k in self._proxy_signals:
            if self._proxy_agent.remote_pub_endpoint.find("*") != -1:
                signal_endpoint = "tcp://*:"+remote_endpoint.split(":")[-1]
            else:
                signal_endpoint = remote_endpoint
            self._proxy_agent._signals[(signal_endpoint, k)] = \
                self._proxy_agent._signals[(signal_endpoint, k)]

    def __getattr__(self, item):
        if item.startswith('_proxy_'):
            return super(Proxy,self).__getattr__(item)
        if item in self._proxy_attr_as_remote:
            return RemoteAttribute(item, self._proxy_agent.request_server, self._proxy_agent.signal_manager)
        return self._proxy_agent.request_server('get', {'name': item}, item in self._proxy_attr_as_object)

    def __setattr__(self, item, value):
        if item.startswith('_proxy_'):
            super(Proxy, self).__setattr__(item, value)
            return

        return self._proxy_agent.request_server('setattr', {'name': item, 'value': value})

    def _proxy_ping(self,ping_timeout=3000):
        return self._proxy_agent.ping_server(ping_timeout)

    def _proxy_stop_server(self):
        self._proxy_agent.request(self._proxy_agent.remote_rep_endpoint, 'stop')

    def _proxy_stop_me(self):
        self._proxy_agent.stop()

    def __del__(self):
        if hasattr(super(Proxy, self), "_proxy_agent"):
            self._proxy_agent.stop()
