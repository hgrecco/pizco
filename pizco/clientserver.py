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

from . import LOGGER, launch
from .util import Signal
from .agent import Agent

if sys.version_info < (3, 2):
    import futures
else:
    from concurrent import futures


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
        LOGGER.debug('Connecting {} to {}'.format(self.name, fun))
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


class Server(Agent):
    """Serves an object for remote access from a Proxy. A Server can serve a single object.

    :param served_object: object to be served.

    .. seealso:: :class:`.Agent`
    .. seealso:: :class:`.Proxy`
    """

    def __init__(self, served_object, rep_endpoint='tcp://127.0.0.1:0', pub_endpoint='tcp://127.0.0.1:0',
                 ctx=None, loop=None):
        self.served_object = served_object
        self.signal_calls = {}
        super(Server, self).__init__(rep_endpoint, pub_endpoint, ctx, loop)

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
                raise ValueError()
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

            elif action == 'instantiate':
                if self.served_object is not None:
                    return PSMessage('raise', (Exception('Cannot instantiate another object.'),
                                               ''))

                mod_name, class_name = options['class'].rsplit('.', 1)
                mod = __import__(mod_name, fromlist=[class_name])
                klass = getattr(mod, class_name)
                self.served_object = klass(*options['args'], **options['kwargs'])
                return PSMessage('return', None)
            else:
                ret = Exception('invalid message action {}'.format(action))
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
        LOGGER.debug('Emitting {}, {}, {}'.format(topic, args, kwargs))
        self.publish(topic, (args, kwargs))

    def on_subscribe(self, topic, count):
        try:
            signal = getattr(self.served_object, topic)
        except AttributeError:
            return

        if count == 1:
            LOGGER.debug('Connecting {} signal on server'.format(topic))
            #def fun(value, old_value=None, other=None):
            #    LOGGER.debug('ready to emit')
            #    self.emit(topic, value, old_value, other)

            def fun(*args, **kwargs):
                LOGGER.debug('ready to emit')
                self.emit(topic, *args, **kwargs)
            self.signal_calls[topic] = fun
            signal.connect(self.signal_calls[topic])

    def on_unsubscribe(self, topic, count):
        try:
            signal = getattr(self.served_object, topic)
        except AttributeError:
            return
        if count == 0:
            LOGGER.debug('Disconnecting {} signal on server'.format(topic))
            signal.disconnect(self.signal_calls[topic])
            del self.signal_calls[topic]

    @classmethod
    def serve_in_thread(cls, served_cls, args, kwargs,
                        rep_endpoint, pub_endpoint='tcp://127.0.0.1:0'):
        t = threading.Thread(target=cls, args=(None, rep_endpoint, pub_endpoint))
        t.start()
        proxy = Proxy(rep_endpoint)
        proxy._proxy_agent.instantiate(served_cls, args, kwargs)
        return proxy

    @classmethod
    def serve_in_process(cls, served_cls, args, kwargs,
                         rep_endpoint, pub_endpoint='tcp://127.0.0.1:0',
                         verbose=False, gui=False):
        cwd = os.path.dirname(inspect.getfile(served_cls))
        launch(cwd, rep_endpoint, pub_endpoint, verbose, gui)
        import time
        time.sleep(1)
        proxy = Proxy(rep_endpoint)
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
                (hasattr(attr, 'connect') and hasattr(attr, 'disconnect') and hasattr(attr, 'emit')) )

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
        return remotes, objects


class ProxyAgent(Agent):
    """Helper class that handles Proxy to Server communication.

    :param remote_rep_endpoint: REP endpoint of the Server.
    """

    def __init__(self, remote_rep_endpoint):
        super(ProxyAgent, self).__init__()

        self.remote_rep_endpoint = remote_rep_endpoint
        ret = self.request(self.remote_rep_endpoint, 'info')
        self.remote_pub_endpoint = ret['pub_endpoint']

        LOGGER.debug('Started Proxy pointing to REP: {} and PUB: {}'.format(self.remote_rep_endpoint, self.remote_pub_endpoint))
        self._signals = defaultdict(Signal)

        #: Maps msgid to future object.
        self._futures = {}
        #: Subscribe to notifications when a future is finished.
        self.subscribe(self.remote_rep_endpoint, '__future__',
                       self.on_future_completed, self.remote_pub_endpoint)

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
            raise ValueError('Invalid response from Server {}'.format(content))

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
            raise ValueError('Unknown {}'.format(ret_action))

    def signal_manager(self, action, signal_name, fun):
        if action == 'connect':
            if not self._signals[(self.remote_rep_endpoint, signal_name)].slots:
                self.subscribe(self.remote_rep_endpoint, signal_name, None, self.remote_pub_endpoint)
            self._signals[(self.remote_rep_endpoint, signal_name)].connect(fun)
        elif action == 'disconnect':
            self._signals[(self.remote_rep_endpoint, signal_name)].disconnect(fun)
            if not self._signals[(self.remote_rep_endpoint, signal_name)].slots:
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
            self._signals[(sender, topic)].emit(*content)
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

    def __init__(self, remote_endpoint):
        self._proxy_agent = ProxyAgent(remote_endpoint)
        self._proxy_attr_as_remote, self._proxy_attr_as_object = self._proxy_agent.request_server('inspect', {})
        
    def __getattr__(self, item):
        if item.startswith('_proxy_'):
            return super(Proxy, self).__getattr__(item)
        if item in self._proxy_attr_as_remote:
            return RemoteAttribute(item, self._proxy_agent.request_server, self._proxy_agent.signal_manager)
        return self._proxy_agent.request_server('get', {'name': item}, item in self._proxy_attr_as_object)

    def __setattr__(self, item, value):
        if item.startswith('_proxy_'):
            super(Proxy, self).__setattr__(item, value)
            return

        return self._proxy_agent.request_server('setattr', {'name': item, 'value': value})

    def _proxy_stop_server(self):
        self._proxy_agent.request(self._proxy_agent.remote_rep_endpoint, 'stop')

    def _proxy_stop_me(self):
        self._proxy_agent.stop()

    def __del__(self):
        self._proxy_agent.stop()
