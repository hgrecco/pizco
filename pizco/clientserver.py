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

    def emit(self, value, old_value, other):
        self.signal_manager('emit', self.name, (value, old_value, other))


def PSMessage(destination, action, options):
    """Builds a message
    """
    return 'PSMessage', destination, action, options


class ServedObject(object):
    """Serves an object for remote access from a Proxy. A Server can serve a single object.

    """

    def __init__(self, server, served_object):
        self.server = server
        self.served_object = served_object

    def exec(self, attr_name, method_name, args=(), kwargs=None):
        """Execute a method from an attribute served object.

        :param attr_name: name of the attribute.
        :param method_name: name of the method
        :param args: positional arguments for the method.
        :param kwargs: keyword arguments for the method.
        :return: The return value of the method.
        """
        attr = getattr(self.served_object, attr_name)
        meth = getattr(attr, method_name)
        return meth(*args, **(kwargs or {}))

    def get(self, attr_name, force_as_object):
        """Get an attribute from the served object, returning a remote object
        when necessary.

        :param attr_name: name of the attribute.
        :param force_as_object: boolean to indicate
        :return:
        """
        attr = getattr(self.served_object, attr_name)
        if force_as_object or self.server.force_as_object(attr):
            return attr
        elif self.server.return_as_remote(attr):
            return PSMessage('remote', None)
        return attr

    def getattr(self, attr_name):
        """Get an attribute from the served object.

        :param object_name: name of the object.
        :param attr_name: name of the attribute
        :return: The attribute value.
        """
        return getattr(self.served_object, attr_name)

    def setattr(self, object_name, attr_name, value):
        """Set an attribute to the served object.

        :param object_name: name of the object.
        :param attr_name: name of the attribute.
        :param value: The new value.
        """
        return setattr(self.served_object, attr_name, value)

    def inspect(self):
        """Inspect the served object and return a tuple containing::

        - a set with the attributes that should be returned as RemoteAttribute.
        - a set with the attributes that should be returned as Objects.

        Override this function to customize your server.
        .. seealso: return_as_remote, force_as_object
        """
        return_as_remote = self.server.return_as_remote
        force_as_object = self.server.force_as_object
        served_object = self.served_object
        remotes = set([name for name, value in inspect.getmembers(served_object)
                       if not name.startswith('_') and return_as_remote(value)])
        objects = set([name for name, value in inspect.getmembers(served_object)
                       if not name.startswith('_') and force_as_object(value)])
        return remotes, objects

    def dispatcher(self, action, options):
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

        if action not in ('exec', 'getattr', 'setattr', 'get'):
            ret = Exception('invalid message action {}'.format(action))
            return PSMessage('raise', (ret, ''))

        try:
            method = getattr(self, action)

            return method(**options)

        except Exception as ex:
            exc_type, exc_value, exc_tb = sys.exc_info()
            tb = traceback.format_exception(exc_type, exc_value, exc_tb)[1:]
            return PSMessage('raise', None, (ex, tb))


class Server(Agent):
    """Serves an object for remote access from a Proxy. A Server can serve a single object.

    .. seealso:: :class:`.Agent`
    .. seealso:: :class:`.Proxy`
    """

    def __init__(self, rep_endpoint='tcp://127.0.0.1:0', pub_endpoint='tcp://127.0.0.1:0',
                 ctx=None, loop=None):

        #: Maps object name to objects.
        self.served_objects = {None: self}

        #: Map a topic to a function to be called when the topic is received.
        self.signal_calls = {}
        super().__init__(rep_endpoint, pub_endpoint, ctx, loop)

    def add_object(self, name, served_object):
        self.served_objects[name] = ServedObject(served_object)

    def list_objects(self):
        """Return a dictionary of served objections {name: class name}

        :return: dict
        """
        return {name: obj.__class__.__name__
                for name, obj in self.served_objects.items()}

    def instantiate(self, object_name, class_name, args=(), kwargs=None):
        """Instantiate a remote object.

        :param object_name: name of the object.
        :param class_name: name of the class.
        """
        if object_name in self.served_objects:
            return PSMessage('raise',
                             (Exception('Cannot instantiate another object with the same.'), ''))

        mod_name, class_name = class_name.rsplit('.', 1)
        mod = __import__(mod_name, fromlist=[class_name])
        klass = getattr(mod, class_name)
        self.add_object(object_name, klass(*args, **(kwargs or {})))

    def dispatcher(self, action, options):

        if action not in ('instantiate', 'inspect'):
            ret = Exception('invalid message action {}'.format(action))
            return PSMessage('raise', None, (ret, ''))

        try:
            method = getattr(self, action)

            return method(**options)

        except Exception as ex:
            exc_type, exc_value, exc_tb = sys.exc_info()
            tb = traceback.format_exception(exc_type, exc_value, exc_tb)[1:]
            return PSMessage('raise', None, (ex, tb))

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
            content_type, destination, action, options = content
            if content_type != 'PSMessage':
                raise ValueError()
        except:
            return super().on_request(sender, topic, content, msgid)

        try:
            obj = self.served_objects[destination]
        except KeyError:
            return PSMessage('raise', None, '{} is not an object in this server'.format(destination))

        ret = obj.dispatcher(action, options)

        if isinstance(ret, PSMessage):
            return ret

        if isinstance(ret, futures.Future):
            def _callback(fut):
                self.publish('__future__',
                             {'msgid': msgid,
                              'result': fut.result() if not fut.exception() else None,
                              'exception': fut.exception()})
            ret.add_done_callback(_callback)
            return PSMessage('future_register', None, msgid)

        return PSMessage('return', None, ret)

    def emit(self, topic, value, old_value, other):
        LOGGER.debug('Emitting {}, {}, {}, {}'.format(topic, value, old_value, other))
        self.publish(topic, (value, old_value, other))

    def on_subscribe(self, topic, count):
        try:
            signal = getattr(self.served_object, topic)
        except AttributeError:
            return

        if count == 1:
            LOGGER.debug('Connecting {} signal on server'.format(topic))
            def fun(value, old_value=None, other=None):
                LOGGER.debug('ready to emit')
                self.emit(topic, value, old_value, other)
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
        proxy._proxy_agent.remote_instantiate(served_cls, args, kwargs)
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
        proxy._proxy_agent.remote_instantiate(served_cls, args, kwargs)
        return proxy

    def serve_forever(self):
        self.join()
        LOGGER.debug('Server stopped')


class SingleServer(Server):
    """A server to serve a single object

    :param served_object: object to be served.

    """
    def __init__(self, served_object, rep_endpoint='tcp://127.0.0.1:0', pub_endpoint='tcp://127.0.0.1:0',
                 ctx=None, loop=None):
        super().__init__(rep_endpoint, pub_endpoint, ctx, loop)
        self.add_object('default', served_object)


class ProxyAgent(Agent):
    """Helper class that handles Proxy to Server communication.

    :param remote_rep_endpoint: REP endpoint of the Server.
    """

    def __init__(self, remote_rep_endpoint):
        super().__init__()

        self.remote_object_name = ??

        self.remote_rep_endpoint = remote_rep_endpoint
        ret = self.request(self.remote_rep_endpoint, 'info')
        self.remote_pub_endpoint = ret['pub_endpoint']

        LOGGER.debug('Started Proxy pointing '
                     'to REP: {} and PUB: {}'.format(self.remote_rep_endpoint, self.remote_pub_endpoint))
        self._signals = defaultdict(Signal)

        #: Maps msgid to future object.
        self._futures = {}
        #: Subscribe to notifications when a future is finished.
        self.subscribe(self.remote_rep_endpoint, '__future__',
                       self.on_future_completed, self.remote_pub_endpoint)

    def remote_exec(self, attr_name, method_name, args=(), kwargs=None):
        return self.request_server('exec', attr_name=attr_name, method_name=method_name,
                                   args=args, kwargs=kwargs)

    def remote_get(self, attr_name, force_as_object):
        return self.request_server('get', force_as_object=force_as_object, attr_name=attr_name)

    def remote_getattr(self, attr_name):
        return self.request_server('getattr', attr_name=attr_name)

    def remote_setattr(self, attr_name, value):
        return self.request_server('setattr', attr_name=attr_name,
                                   value=value)

    def remote_inspect(self):
        return self.request_server('getattr')

    def remote_instantiate(self, object_name, class_name, args=(), kwargs=None):
        if not isinstance(class_name, str):
            class_name = class_name.__module__ + '.' + class_name.__name__

        self.request_server('instantiate', object_name=object_name, class_name=class_name,
                            args=args, kwargs=kwargs)

    def request_server(self, action, **options):
        """Sends a request to the associated server using PSMessage

        :param action: action to be sent.
        :param options: options of the action.
        :return:
        """
        options['object_name'] = self.remote_object_name
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
            super().on_notification(sender, topic, content, msgid)


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
        self._proxy_attr_as_remote, self._proxy_attr_as_object = self._proxy_agent.remote_inspect()
        
    def __getattr__(self, item):
        if item.startswith('_proxy_'):
            return super().__getattr__(item)
        if item in self._proxy_attr_as_remote:
            return RemoteAttribute(item, self._proxy_agent.request_server, self._proxy_agent.signal_manager)
        return self._proxy_agent.remote_get(item, item in self._proxy_attr_as_object)

    def __setattr__(self, item, value):
        if item.startswith('_proxy_'):
            super().__setattr__(item, value)
            return

        return self._proxy_agent.remote_setattr(item, value)

    def _proxy_stop_server(self):
        self._proxy_agent.request(self._proxy_agent.remote_rep_endpoint, 'stop')

    def _proxy_stop_me(self):
        self._proxy_agent.stop()

    def __del__(self):
        self._proxy_agent.stop()
