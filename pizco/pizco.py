# -*- coding: utf-8 -*-
"""
    pyzco
    ~~~~~

    A small remoting framework with notification and async commands using ZMQ.

    :copyright: 2012 by Lantz Authors, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""


import os
import sys
import uuid
import hmac
import json
import pickle
import weakref
import hashlib
import inspect
import logging
import threading
import subprocess
from concurrent import futures

from collections import defaultdict

if sys.version_info < (3, 0):
    try:
        import cPickle as pickle
    except ImportError:
        pass

if sys.version_info < (3, 3):
    def compare_digest(a, b):
        return a == b
else:
    compare_digest = hmac.compare_digest

import zmq
from zmq.eventloop import zmqstream, ioloop

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

DEFAULT_LAUNCHER = os.environ.get('PZC_DEFAULT_LAUNCHER', None)

if not DEFAULT_LAUNCHER:
    sw = sys.platform.startswith
    if sw('linux'):
        DEFAULT_LAUNCHER = r"""xterm -e "{0[python]} {0[pizco]} {0[rep_endpoint]} {0[pub_endpoint]} -p {0[cwd]} {0[verbose]} """
    elif sw('win32'):
        DEFAULT_LAUNCHER = r"""cmd.exe /k "{0[python]} {0[pizco]} {0[rep_endpoint]} {0[pub_endpoint]} -p {0[cwd]} {0[verbose]} """
    elif sw('darwin'):
        DEFAULT_LAUNCHER = r"""osascript -e 'tell application "Terminal"' """\
                           r""" -e 'do script "\"{0[python]}\" \"{0[pizco]}\" {0[rep_endpoint]} {0[pub_endpoint]} -p \"{0[cwd]}\" {0[verbose]}"' """\
                           r""" -e 'end tell' """
        #DEFAULT_LAUNCHER = r"""screen -d -m {0[python]} {0[pizco]} {0[rep_endpoint]} {0[pub_endpoint]} -p  {0[cwd]}"""

def _uuid():
    """Generate a unique id for messages.
    """
    return uuid.uuid4().urn


class Signal(object):
    """PyQt like signal object
    """

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
        logger.debug('Connecting {} to {}'.format(self.name, fun))
        self.signal_manager('connect', self.name, fun)

    def disconnect(self, fun):
        self.signal_manager('disconnect', self.name, fun)

    def emit(self, value, old_value, other):
        self.signal_manager('emit', self.name, (value, old_value, other))


class Protocol(object):
    """Communication protocol

    :param hmac_key: signing key. If not given, messages will not be signed.
    :type hmac_key: str
    :param serializer: the name of serialization protocol. Valid names are::

        - 'pickle': use the highest version available of the pickle format (default).
        - 'pickleN': use the N version of the pickle format.
        - 'json': use json format.

    REP/REQ and PUB/SUB Messages have the following format:

    FRAME 0: HEADER+sender identification+topic (str)
    FRAME 1: serialization protocol (str)
    FRAME 2: content (binary)
    FRAME 3: Message ID (str)
    FRAME 4: HMAC sha1 signature of FRAME 0:4 concatenated with Agent.hmac_key
    """

    HEADER = 'PZC00'

    def __init__(self, hmac_key='', serializer=None):
        self.hmac_key = hmac_key.encode('utf-8')
        self.serializer = serializer or 'pickle'

    def parse(self, message, check_sender=None, check_msgid=None):
        """Return a parsed message

        :param message: the message as obtained by socket.recv_multipart.
        :param check_sender: verify that the sender of the message is the one provided.
        :param check_msgid: verify that the identification of the message is equal to the on provided.
        :return: sender, topic, content, msgid
        :raise: ValueError if messages is malformed or verification fails.
        """

        return self._parse(self.hmac_key, message, check_sender, check_msgid)

    def _parse(self, key, message, check_sender=None, check_msgid=None):

        try:
            signed, signature = message[:4], message[4]
        except:
            raise ValueError('The message has the wrong number of parts. Expected 5, received: {}'.format(len(message)))

        if key and not compare_digest(self._signature(key, signed), signature):
            raise ValueError('The signature does not match.')

        full_header, serializer, content, msgid = signed
        try:
            header, sender, topic = full_header.decode('utf-8').split('+')
            msgid = msgid.decode('utf-8')
            serializer = serializer.decode('utf-8')
        except:
            raise ValueError('Could not decode or split message parts from UTF-8 bytes.')

        if header != self.HEADER:
            raise ValueError('Wrong header. In server: {}, received: {}'.format(self.HEADER, header))

        if check_sender and check_sender != sender:
            raise ValueError('Wrong Sender Sender. Sent: {}, received: {}'.format(check_sender, msgid))

        if check_msgid and check_msgid != msgid:
            raise ValueError('Wrong Message ID. Sent: {}, received: {}'.format(check_msgid, msgid))

        try:
            if serializer.startswith('pickle'):
                content = pickle.loads(content)
            elif serializer == 'json':
                content = json.loads(content)
            else:
                raise ValueError('Invalid serializer: {}'.format(serializer))
        except Exception as ex:
            raise ValueError('Could not deserialize content: {}'.format(ex))

        return sender, topic, content, msgid

    def format(self, sender, topic='', content='', msgid=None, just_header=False):
        """Return a formatted message.

        :param sender: unique identifier of the sender as string.
        :param topic: topic of the message as string.
        :param content: content of the message as str.
        :param msgid: message identifier as str. If None, a unique number will be generated
        :param just_header: Return only the header
        :return: formatted message
        :rtype: list of bytes
        """
        return self._format(self.hmac_key, self.serializer, sender, topic, content, msgid, just_header)

    def _format(self, key, serializer, sender, topic='', content='', msgid=None, just_header=False):
        try:
            if serializer.startswith('pickle'):
                version = int(serializer[6:] or -1)
                content = pickle.dumps(content, version)
            elif serializer == 'json':
                content = json.dumps(content).encode('utf-8')
            else:
                raise ValueError('Unknown serializer {}'.format(serializer))
        except Exception as ex:
            raise ValueError('Could not serialize content with {}'.format(ex))

        if just_header:
            return (self.HEADER + '+' + sender + '+' + topic).encode('utf-8')
        parts = [(self.HEADER + '+' + sender + '+' + topic).encode('utf-8'),
                 serializer.encode('utf-8'),
                 content,
                 (msgid or _uuid()).encode('utf-8')]
        return parts + [self._signature(key, parts), ]

    def _signature(self, key, parts):
        if not key:
            return b''
        msg = sum(parts, b'')
        return hmac.new(key, msg, digestmod=hashlib.sha1).digest()


class AgentManager(object):

    agents = weakref.WeakKeyDictionary()
    threads = weakref.WeakKeyDictionary()
    in_use = weakref.WeakSet()

    @classmethod
    def add(cls, agent):
        loop = agent.loop
        try:
            cls.agents[loop].append(agent)
        except KeyError:
            t = threading.Thread(target=loop.start, name='ioloop-{}'.format(id(loop)))
            cls.agents[loop] = [agent, ]
            cls.threads[loop] = t
            cls.in_use.add(loop)
            t.daemon = True
            t.start()

    @classmethod
    def remove(cls, agent):
        loop = agent.loop
        cls.agents[loop].remove(agent)
        if not cls.agents[loop] and loop in cls.in_use:
            cls.in_use.remove(loop)
            loop.add_callback(lambda: loop.stop)

    @classmethod
    def join(cls, agent):
        cls.threads[agent.loop].join()


class Agent(object):
    """An object that can communicate via ZMQ to other Agents.

    Each agent has:
    - a REP socket to receive requests
    - one REQ per each Agent that it has to talk to (stored in self.connections)
    - one PUB to emit notifications
    - one SUB to subscribe to notifications

    Messages are parsed and formatted by the Protocol Class

    :param rep_endpoint: endpoint of the REP socket.
    :param pub_endpoint: endpoint of the PUB socket.
    :param ctx: ZMQ context, if None will use default context.
    :param loop: ZMQ event loop, if None will use default loop.
    """

    def __init__(self, rep_endpoint='tcp://127.0.0.1:0', pub_endpoint='tcp://127.0.0.1:0',
                 ctx=None, loop=None, protocol=None):

        self.ctx = ctx or zmq.Context.instance()
        self.loop = loop or ioloop.IOLoop.instance()
        self.protocol = protocol or Protocol(os.environ.get('PZC_KEY', ''))
        logger.debug('New agent at {} with context {} and loop {}'.format(rep_endpoint, self.ctx, self.loop))

        #: Connections to other agents (endpoint:REQ socket)
        self.connections = {}

        #: Incoming request sockets
        rep = self.ctx.socket(zmq.REP)
        self.rep_endpoint = bind(rep, rep_endpoint)

        logger.debug('Bound rep at {} REP.'.format(self.rep_endpoint, self.rep_endpoint))

        #: Subscribers per topics (topic:count of subscribers)
        self.subscribers = defaultdict(int)

        #: Outgoing notification socket
        pub = self.ctx.socket(zmq.XPUB)
        self.pub_endpoint = bind(pub, pub_endpoint)

        logger.debug('{} PUB: {}'.format(self.rep_endpoint, self.pub_endpoint))

        #: Incoming notification socket
        sub = self.ctx.socket(zmq.SUB)
        self.sub_endpoint = bind(sub)
        logger.debug('{} SUB: {}'.format(self.rep_endpoint, self.sub_endpoint))

        #: dict (sender, topic), callback(sender, topic, payload)
        self.notifications_callbacks = {}
        #: endpoints to which the socket is connected.
        self.sub_connections = set()

        self.rep_to_pub = {}

        #Transforms sockets into Streams in the loop, add callbacks and start loop if necessary.
        self._start(rep, pub, sub)

    def _start(self, rep, pub, sub, in_callback=False):
        AgentManager.add(self)
        if not in_callback:
            self.loop.add_callback(lambda: self._start(rep, pub, sub, True))
        else:
            self.rep = zmqstream.ZMQStream(rep, self.loop)
            self.pub = zmqstream.ZMQStream(pub, self.loop)
            self.sub = zmqstream.ZMQStream(sub, self.loop)
            self.rep.on_recv_stream(self._on_request)
            self.pub.on_recv_stream(self._on_incoming_xpub)
            self.sub.on_recv_stream(self._on_notification)

            self._running = True

            logger.info('Started agent {}'.format(self.rep_endpoint))

    def stop(self):
        """Stop actor unsubscribing from all notification and closing the streams.
        """
        if not self._running:
            return

        #self.publish('__status__', 'stop')
        #for (endpoint, topic) in list(self.notifications_callbacks.keys()):
        #    self.unsubscribe(endpoint, topic)

        for stream in (self.rep, self.pub, self.sub):
            self.loop.add_callback(lambda: stream.on_recv(None))
            self.loop.add_callback(stream.flush)
            self.loop.add_callback(stream.close)
        for sock in self.connections.values():
            self.loop.add_callback(sock.close)
        self.connections = {}
        AgentManager.remove(self)
        self._running = False
        logger.info('Stopped agent {}'.format(self.rep_endpoint))

    def __del__(self):
        self.stop()

    def request(self, recipient, content):
        """Send a request to another agent and waits for the response.

        Messages have the following structure (sender name, message id, content)
        This methods is executed in the calling thread.

        :param recipient: endpoint of the recipient.
        :param content: content to be sent.
        :return: The response of recipient.
        """
        logger.debug('{} -> {}: {}'.format(self, recipient, content))
        try:
            req = self.connections[recipient]
        except KeyError:
            req = self.ctx.socket(zmq.REQ)
            req.connect(recipient)

            self.connections[recipient] = req

        msgid = req.send_multipart(self.protocol.format(self.rep_endpoint, '', content, None))
        sender, topic, content, msgid = self.protocol.parse(req.recv_multipart(), recipient, msgid)
        return content

    def _on_request(self, stream, message):
        """Handles incoming requests from other agents, dispatch them to
        on_request and send the response back on the same stream.

        Messages have the following structure (sender name, message id, message)
        This methods is executed in the IOLoop thread.
        """
        try:
            sender, topic, content, msgid = self.protocol.parse(message)
        except Exception as ex:
            topic = ret = msgid = ''
            logger.debug(ex)
        else:
            logger.debug('{} <- {}: ({}) {}'.format(self.rep_endpoint, sender, msgid, content))
            ret = self.on_request(sender, topic, content, msgid)
            logger.debug('Return value for {}: {}'.format(msgid, ret))

        stream.send_multipart(self.protocol.format(self.rep_endpoint, topic, ret, msgid))

    def on_request(self, sender, topic, content, msgid):
        """Handles incoming request from other agents and return the response
        that should be sent to the source.

        Overload this method on your class to provide an specific behaviour.
        Call super to enable

        This methods is executed in the IOLoop thread.

        :param sender: name of the sender.
        :param topic: topic of the message.
        :param content: content of the message.
        :param msgid: unique id of the message.
        :return: message to be sent to the sender
        """
        if content == 'info':
            return {'rep_endpoint': self.rep_endpoint,
                    'pub_endpoint': self.pub_endpoint}
        elif content == 'stop':
            cb = ioloop.DelayedCallback(self.stop, .1, self.loop)
            cb.start()
            return 'stopping'
        return content

    def _publish(self, topic, content):
        """Publish a message to the PUB socket.

        This methods must be executed in IOLoop thread.

        """

        self.pub.send_multipart(self.protocol.format(self.rep_endpoint, topic, content))

    def publish(self, topic, content):
        """Thread safe publish of a message to the PUB socket.

        The full topic is built from concatenating endpoint + '+' + topic

        Messages have the following structure: topic <STOP> (sender, message id, content)
        This method is executed in the calling thread, the actual publishing is done the IOLoop.

        :param topic: topic of the message.
        :param content: content of the message.
        """
        self.loop.add_callback(lambda: self._publish(topic, content))

    def _on_incoming_xpub(self, stream, message):
        """Handles incoming message in the XPUB sockets, increments or decrements the subscribers
        per topic and dispatch to on_subscribe, on_unsubscribe
        Messages contain a byte indicating if a subscription or unsubscription and the topic.

        This methods is executed in the IOLoop thread.
        """
        try:
            message = message[0]
            action, full_topic = message[0] == 1, message[1:].decode("utf-8")
            protocol, source, topic = full_topic.split('+')
        except Exception as ex:
            logger.debug('Invalid message from {}: {}\n{}'.format(stream, message, ex))
            return

        logger.debug('Incoming XPUB {} {}'.format(action, topic))

        if action:
            self.subscribers[topic] += 1
            self.on_subscribe(topic, self.subscribers[topic])
        elif self.subscribers[topic] > 0:
            self.subscribers[topic] -= 1
            self.on_unsubscribe(topic, self.subscribers[topic])

    def on_subscribe(self, topic, count):
        """Callback for incoming subscriptions.

        This methods is executed in the IOLoop thread.

        :param topic: a string with the topic.
        :param count: number of subscribers
        """

    def on_unsubscribe(self, topic, count):
        """Callback for incoming unsubscriptions.

        This methods is executed in the IOLoop thread.

        :param topic: a string with the topic.
        :param count: number of subscribers
        """

    def _subscribe(self, endpoint, agentid_topic):
        """Subscribe to a topic at endpoint.

        This methods must be executed in IOLoop thread.
        """
        if endpoint not in self.sub_connections:
            self.sub.connect(endpoint)
            self.sub_connections.add(endpoint)
        self.sub.setsockopt(zmq.SUBSCRIBE, agentid_topic)
        logger.debug('Subscription sent to {}'.format(agentid_topic))

    def _unsubscribe(self, endpoint, agentid_topic):
        """Unsubscribe to a topic at endpoint.

        This methods must be executed in IOLoop thread.
        """
        self.sub.setsockopt(zmq.UNSUBSCRIBE, agentid_topic)
        logger.debug('Unsubscription sent to {}'.format(agentid_topic))

    def subscribe(self, rep_endpoint, topic, callback=None, pub_endpoint=None):
        """Thread safe subscribe to a topic at endpoint from another agent
        and assign a callback for the specific endpoint and topic.

        The full topic is built from concatenating PROTOCOL_HEADER + '+' + endpoint + '+' + topic

        Notice that Agent.subscribe_to_agent takes the rep_endpoint
        of the other agent.

        This method will be executed in main thread, the actual subscription is done the IOLoop.

        :param rep_endpoint: endpoint of an agent REP socket.
        :param topic: a string with the topic to subscribe.
        :param callback: a callable with the (sender, topic, content)
        :param pub_endpoint: endpoint of an agent PUB socket, if not given it will be queried.
        """
        pub_endpoint = pub_endpoint or self.rep_to_pub.get(rep_endpoint, None)
        if not pub_endpoint:
            ret = self.request(rep_endpoint, 'info')
            pub_endpoint = ret['pub_endpoint']
            self.rep_to_pub[rep_endpoint] = pub_endpoint
        elif rep_endpoint not in [rep_endpoint]:
            self.rep_to_pub[rep_endpoint] = pub_endpoint

        agentid_topic  = self.protocol.format(rep_endpoint, topic, just_header=True)
        logger.debug('Subscribing to {} with {}'.format(agentid_topic, callback))
        self.loop.add_callback(lambda: self._subscribe(pub_endpoint, agentid_topic))
        self.notifications_callbacks[(rep_endpoint, topic)] = callback

    def unsubscribe(self, rep_endpoint, topic, pub_endpoint=None):
        """Thread safe unsubscribe to a topic at endpoint and assign a callback
        for the specific endpoint and topic.

        This method will be executed in main thread, the actual unsubscription is done the IOLoop.

        :param rep_endpoint: endpoint of an agent REP socket.
        :param topic: a string with the topic to subscribe.
        :param pub_endpoint: endpoint of an agent PUB socket, if not given it will be queried.
        """
        pub_endpoint = pub_endpoint or self.rep_to_pub.get(rep_endpoint, None)
        if not pub_endpoint:
            ret = self.request(rep_endpoint, 'info')
            pub_endpoint = ret['pub_endpoint']
            self.rep_to_pub[rep_endpoint] = pub_endpoint

        agentid_topic  = self.protocol.format(rep_endpoint, topic, just_header=True)
        logger.debug('Unsubscribing to {}'.format(agentid_topic))
        self.loop.add_callback(lambda: self._unsubscribe(pub_endpoint, agentid_topic))
        del self.notifications_callbacks[(rep_endpoint, topic)]

    def _on_notification(self, stream, message):
        """Handles incoming messages in the SUB socket dispatching to a callback if provided or
        to on_notification.

        This methods is executed in the IOLoop thread.
        """
        try:
            sender, topic, content, msgid = self.protocol.parse(message)
        except:
            logger.debug('Invalid message {}'.format(message))
        else:
            callback = self.notifications_callbacks[(sender, topic)]
            if callback:
                callback(sender, topic, content, msgid)
            else:
                self.on_notification(sender, topic, content, msgid)

    def on_notification(self, sender, topic, content, msgid):
        """Default notification callback for (sender, topic) in which a callback is not provided.

        Override this method to provide a custom behaviour.
        This methods is executed in the IOLoop thread.

        :param sender: sender of the notification.
        :param topic: topic of the notification.
        :param content: content of the notification.
        :param msgid: message id.
        """
        logger.debug('Received notification: {}, {}, {}, {}'.format(sender, topic, msgid, content))


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

    def __init__(self, served_object, rep_endpoint='tcp://127.0.0.1:0', pub_endpoint='tcp://127.0.0.1:0', ctx=None, loop=None):
        self.served_object = served_object
        self.signal_calls = {}
        super().__init__(rep_endpoint, pub_endpoint, ctx, loop)

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
            return super().on_request(sender, topic, content, msgid)

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
                    return PSMessage('raise', Exception('Cannot instantiate another object.'))

                mod_name, class_name = options['class'].rsplit('.', 1)
                mod = __import__(mod_name, fromlist=[class_name])
                klass = getattr(mod, class_name)
                self.served_object = klass(*options['args'], **options['kwargs'])
                return PSMessage('return', None)
            else:
                ret = Exception('invalid message action {}'.format(action))
                return PSMessage('raise', ret)

            if isinstance(ret, futures.Future):
                ret.add_done_callback(lambda fut: self.publish('__future__',
                                                               {'msgid': msgid,
                                                                'result': fut.result() if not fut.exception() else None,
                                                                'exception': fut.exception()}))
                return PSMessage('future_register', msgid)

            return PSMessage('return', ret)

        except Exception as ex:
            return PSMessage('raise', ex)

    def emit(self, topic, value, old_value, other):
        logger.debug('Emitting {}, {}, {}, {}'.format(topic, value, old_value, other))
        self.publish(topic, (value, old_value, other))

    def on_subscribe(self, topic, count):
        try:
            signal = getattr(self.served_object, topic)
        except AttributeError:
            return

        if count == 1:
            logger.debug('Connecting {} signal on server'.format(topic))
            def fun(value, old_value=None, other=None):
                logger.debug('ready to emit')
                self.emit(topic, value, old_value, other)
            self.signal_calls[topic] = fun
            signal.connect(self.signal_calls[topic])

    def on_unsubscribe(self, topic, count):
        try:
            signal = getattr(self.served_object, topic)
        except AttributeError:
            return
        if count == 0:
            logger.debug('Disconnecting {} signal on server'.format(topic))
            signal.disconnect(self.signal_calls[topic])
            del self.signal_calls[topic]

    @classmethod
    def serve_in_thread(cls, served_cls, args, kwargs, rep_endpoint, pub_endpoint='tcp://127.0.0.1:0'):
        t = threading.Thread(target=cls, args=(None, rep_endpoint, pub_endpoint), kwargs={'ctx': zmq.Context.instance(),
                                                                                          'loop': ioloop.IOLoop.instance()})
        t.start()
        proxy = Proxy(rep_endpoint)
        proxy._proxy_agent.instantiate(served_cls, args, kwargs)
        return proxy

    @classmethod
    def serve_in_process(cls, served_cls, args, kwargs, rep_endpoint, pub_endpoint='tcp://127.0.0.1:0', verbose=False, gui=True):
        cwd = os.path.dirname(inspect.getfile(served_cls))
        o = dict(python=sys.executable, pizco=__file__, rep_endpoint=rep_endpoint, pub_endpoint=pub_endpoint, cwd=cwd, verbose='')
        if verbose:
            o['verbose'] = '-v'

        if gui:
            cmd = '{0[python]} {0[pizco]} {0[rep_endpoint]} {0[pub_endpoint]} -p  {0[cwd]} -g {0[verbose]}'.format(o)
        else:
            cmd = DEFAULT_LAUNCHER.format(o)

        subprocess.Popen(cmd, cwd=cwd, shell=True)
        import time
        time.sleep(1)
        proxy = Proxy(rep_endpoint)
        proxy._proxy_agent.instantiate(served_cls, args, kwargs)
        return proxy

    def serve_forever(self):
        AgentManager.join(self)
        logger.debug('Server stopped')

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
        super().__init__()

        self.remote_rep_endpoint = remote_rep_endpoint
        ret = self.request(self.remote_rep_endpoint, 'info')
        self.remote_pub_endpoint = ret['pub_endpoint']

        logger.debug('Started Proxy pointing to REP: {} and PUB: {}'.format(self.remote_rep_endpoint, self.remote_pub_endpoint))
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
            raise ret_options
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

    def instantiate(self, served_cls, args, kwargs):
        if not isinstance(served_cls, str):
            served_cls = served_cls.__module__ + '.' + served_cls.__name__
        self.request_server('instantiate', {'class': served_cls, 'args': args, 'kwargs': kwargs})


class Proxy(object):
    """Proxy object to access a server.

    :param remote_endpoint: endpoint of the server.
    """

    def __init__(self, remote_endpoint):
        self._proxy_agent = ProxyAgent(remote_endpoint)
        self._proxy_attr_as_remote, self._proxy_attr_as_object = self._proxy_agent.request_server('inspect', {})
        
    def __getattr__(self, item):
        if item.startswith('_proxy_'):
            return super().__getattr__(item)
        if item in self._proxy_attr_as_remote:
            return RemoteAttribute(item, self._proxy_agent.request_server, self._proxy_agent.signal_manager)
        return self._proxy_agent.request_server('get', {'name': item}, item in self._proxy_attr_as_object)

    def __setattr__(self, item, value):
        if item.startswith('_proxy_'):
            super().__setattr__(item, value)
            return

        return self._proxy_agent.request_server('setattr', {'name': item, 'value': value})

    def _proxy_stop_server(self):
        self._proxy_agent.request(self._proxy_agent.remote_rep_endpoint, 'stop')

    def _proxy_stop_me(self):
        self._proxy_agent.stop()

    def __del__(self):
        self._proxy_agent.stop()

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser('Starts an server')
    parser.add_argument('-g', '--gui', action='store_true',
                        help='Open a small window to display the server status.')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Print debug information to the console.')
    parser.add_argument('-p', '--path', type=str,
                        help='Append this path to sys.path')
    parser.add_argument('rep_endpoint',
                        help='REP endpoint of the Server')
    parser.add_argument('pub_endpoint',
                        help='PUB endpoint of the Server')

    args = parser.parse_args()

    if args.path:
        sys.path.append(args.path)

    if args.verbose:
        logger.addHandler(logging.StreamHandler())
        logger.setLevel(logging.DEBUG)

    s = Server(None, args.rep_endpoint, args.pub_endpoint)
    print('Server started at {}'.format(s.rep_endpoint))
    if args.gui:
        if sys.version_info < (3, 0):
            from TKinter import Tk, Label
        else:
            from tkinter import Tk, Label

        import time

        while s.served_object is None:
            time.sleep(.1)

        name = s.served_object.__class__.__name__

        root = Tk()
        root.title('Pizco Server: {}'.format(name))
        Label(root, text='{}'.format(name)).pack(padx=5)
        Label(root, text='REP: {}'.format(s.rep_endpoint)).pack(padx=5)
        Label(root, text='PUB: {}'.format(s.pub_endpoint)).pack(padx=5)
        root.resizable(width=False, height=False)
        root.mainloop()
    else:
        print('Press CTRL+c to stop ...')
        s.serve_forever()

    print('Server stopped')

