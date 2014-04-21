# -*- coding: utf-8 -*-

import time
import operator
import unittest
import threading

from threading import Thread

from concurrent.futures import ThreadPoolExecutor
import zmq


def set_zmq_context_to_none():
    if hasattr(zmq.Context, '_instance'):
        zmq.Context._instance = None
    else:
        zmq.context._instance = None

from pizco import Proxy, Server, Agent, Signal
from pizco.protocol import Protocol

PROTOCOL_HEADER = Protocol.HEADER

SLEEP_SECS = .1

executor = ThreadPoolExecutor(max_workers=1)


class Add1(Agent):

    def on_request(self, sender, topic, content, msgid):
        return content + 1


class NoInspectServer(Server):

    def inspect(self):
        return set(), set(), set()


class ReturnDictsServer(Server):

    def force_as_object(self, attr):
        return isinstance(attr, dict)

    def return_as_remote(self, attr):
        return False

    def is_signal(self, attr):
        return False


class Example(object):

    def __init__(self):
        self.simple_attribute = 12
        self._private_value = 42
        self.dict_attribute = {1: 2}

        self._rw_prop = 42
        self._ro_prop = 42
        self._wo_prop = 42
        self.rw_prop_changed = Signal(nargs=1)
        self.wo_prop_changed = Signal(nargs=1)


    @property
    def rw_prop(self):
        return self._rw_prop

    @rw_prop.setter
    def rw_prop(self, value):
        if self._rw_prop == value:
            return
        self.rw_prop_changed.emit(value)
        self._rw_prop = value

    @property
    def ro_prop(self):
        return self._ro_prop

    def wo_prop(self, value):
        if self._wo_prop == value:
            return
        self.wo_prop_changed.emit(value)
        self._wo_prop = value

    wo_prop = property(None, wo_prop)

    def fun_simple(self):
        return 46

    def fun_arg1(self, x):
        return x + 2

    def fun_arg2(self, x=2, y=3):
        return x ** y

    def fun_raise(self):
        raise ValueError('Bla')

    def fut(self):
        def fun():
            time.sleep(1)
            return 10
        return executor.submit(fun)

    def fut_raise(self):
        def fun():
            time.sleep(1)
            raise ValueError
        return executor.submit(fun)




lock = threading.RLock()

class AgentTest(unittest.TestCase):

    green = False

    @property
    def Context(self):
        return zmq.Context

    def create_socket(self, type):
        sock = self.context.socket(type)
        self.sockets.append(sock)
        return sock

    def setUp(self):
        self.context = self.Context.instance()
        self.sockets = []

    def tearDown(self):
        time.sleep(.1)  # give things time to stop
        contexts = set([self.context])
        while self.sockets:
            sock = self.sockets.pop()
            contexts.add(sock.context) # in case additional contexts are created
            sock.close(0)
        for ctx in contexts:
            t = Thread(target=ctx.term)
            t.daemon = True
            t.start()
            t.join(timeout=2)
            if t.is_alive():
                # reset Context.instance, so the failure to term doesn't corrupt subsequent tests
                set_zmq_context_to_none()
                raise RuntimeError("context could not terminate, open sockets likely remain in test")

    def test_agent_rep(self):

        agent = Agent()

        req = self.create_socket(zmq.REQ)
        req.connect(agent.rep_endpoint)

        prot = Protocol()
        msg = prot.format('friend', 'bla', (None, 123, 'Test'))
        req.send_multipart(msg)
        ret = req.recv_multipart()
        sender, topic, content, msgid = prot.parse(ret)

        self.assertEqual(sender, agent.rep_endpoint)
        self.assertEqual(topic, 'bla')
        self.assertEqual(content, (None, 123, 'Test'))

        agent.stop()
        time.sleep(.1)

    def test_agent_stop(self):

        agent = Agent()
        agent_ctrl = Agent()

        ret = agent_ctrl.request(agent.rep_endpoint, 3)
        self.assertEqual(3, ret)

        ret = agent_ctrl.request(agent.rep_endpoint, 'stop')
        self.assertEqual('stopping', ret)

        agent_ctrl.stop()

    def test_agent_serve_in_thread(self):

        address = 'tcp://127.0.0.1:9876'
        proxy = Server.serve_in_thread(Example, (), {}, address)

        time.sleep(SLEEP_SECS)

        self.assertEqual(proxy.simple_attribute, 12)

        proxy._proxy_stop_server()
        proxy._proxy_stop_me()

    def test_agent_serve_in_process(self):

        address = 'tcp://127.0.0.1:9874'
        proxy = Server.serve_in_process(Example, (), {}, address)

        time.sleep(SLEEP_SECS * 10)

        self.assertEqual(proxy.simple_attribute, 12)

        proxy._proxy_stop_server()
        proxy._proxy_stop_me()

    def test_agent_req_agent_rep(self):

        agent1 = Add1()
        agent2 = Add1()

        value = 0
        while value < 100:
            value = agent2.request(agent1.rep_endpoint, value)

        self.assertEqual(value, 100)

        agent1.stop()
        agent2.stop()

    def test_server(self):

        s = Server(Example())

        proxy = Proxy(s.rep_endpoint)
        self.assertEqual(s.served_object.simple_attribute, 12)
        self.assertEqual(proxy.simple_attribute, 12)
        proxy.simple_attribute = 24
        self.assertEqual(s.served_object.simple_attribute, 24)
        self.assertEqual(proxy.simple_attribute, 24)

        self.assertRaises(AttributeError, getattr, proxy, 'not_an_attribute')

        self.assertEqual(s.served_object.dict_attribute[1], 2)
        self.assertEqual(proxy.dict_attribute[1], 2)
        self.assertRaises(KeyError, operator.getitem, proxy.dict_attribute, 2)
        proxy.dict_attribute[2] = 4
        self.assertEqual(s.served_object.dict_attribute[2], 4)
        self.assertEqual(proxy.dict_attribute[2], 4)

        self.assertEqual(s.served_object.rw_prop, 42)
        self.assertEqual(proxy.rw_prop, 42)
        proxy.rw_prop = 21
        self.assertEqual(s.served_object.rw_prop, 21)
        self.assertEqual(proxy.rw_prop, 21)

        self.assertEqual(proxy.fun_simple(), 46)
        self.assertEqual(proxy.fun_arg1(2), 4)
        self.assertEqual(proxy.fun_arg2(2, 3), 8)
        self.assertEqual(proxy.fun_arg2(y=2), 4)

        self.assertRaises(ValueError, proxy.fun_raise)

        proxy._proxy_stop_server()
        proxy._proxy_stop_me()

    def test_server_no_inspect(self):

        s = NoInspectServer(Example())

        proxy = Proxy(s.rep_endpoint)
        self.assertEqual(s.served_object.simple_attribute, 12)
        self.assertEqual(proxy.simple_attribute, 12)
        proxy.simple_attribute = 24
        self.assertEqual(s.served_object.simple_attribute, 24)
        self.assertEqual(proxy.simple_attribute, 24)

        self.assertRaises(AttributeError, getattr, proxy, 'not_an_attribute')

        self.assertEqual(s.served_object.dict_attribute[1], 2)
        self.assertEqual(proxy.dict_attribute[1], 2)
        self.assertRaises(KeyError, operator.getitem, proxy.dict_attribute, 2)
        proxy.dict_attribute[2] = 4
        self.assertEqual(s.served_object.dict_attribute[2], 4)
        self.assertEqual(proxy.dict_attribute[2], 4)

        self.assertEqual(s.served_object.rw_prop, 42)
        self.assertEqual(proxy.rw_prop, 42)
        proxy.rw_prop = 21
        self.assertEqual(s.served_object.rw_prop, 21)
        self.assertEqual(proxy.rw_prop, 21)

        self.assertEqual(proxy.fun_simple(), 46)
        self.assertEqual(proxy.fun_arg1(2), 4)
        self.assertEqual(proxy.fun_arg2(2, 3), 8)
        self.assertEqual(proxy.fun_arg2(y=2), 4)

        self.assertRaises(ValueError, proxy.fun_raise)

        proxy._proxy_stop_server()
        proxy._proxy_stop_me()

    def test_server_return_dict(self):

        s = ReturnDictsServer(Example())

        proxy = Proxy(s.rep_endpoint)

        self.assertEqual(s.served_object.dict_attribute[1], 2)
        self.assertEqual(s.served_object.dict_attribute, {1: 2})
        self.assertEqual(proxy.dict_attribute[1], 2)
        self.assertEqual(proxy.dict_attribute, {1: 2})

        # This should not work as the dictionary is not remotely linked
        proxy.dict_attribute[2] = 4
        self.assertEqual(s.served_object.dict_attribute, {1: 2})

        proxy._proxy_stop_server()
        proxy._proxy_stop_me()

    def test_agent_publish(self):

        prot = Protocol()

        agent = Agent()

        topic1 = 'topic1'
        topic2 = 'topic2'
        sub = self.create_socket(zmq.SUB)
        sub.connect(agent.pub_endpoint)
        sub.setsockopt(zmq.SUBSCRIBE, prot.format(agent.rep_endpoint, topic1, just_header=True))

        time.sleep(SLEEP_SECS)

        self.assertTrue(topic1 in agent.subscribers)
        self.assertEqual(agent.subscribers[topic1], 1)
        self.assertFalse(topic2 in agent.subscribers)

        agent.publish(topic1, 'message')
        sender, topic, content, msgid = prot.parse(sub.recv_multipart())
        self.assertEqual(content, 'message')

        agent.publish(topic2, 'message')
        time.sleep(SLEEP_SECS)
        self.assertRaises(zmq.ZMQError, sub.recv_multipart, flags=zmq.NOBLOCK)

        agent.publish('top', 'message')
        time.sleep(SLEEP_SECS)
        self.assertRaises(zmq.ZMQError, sub.recv_multipart, flags=zmq.NOBLOCK)

        sub.close()
        agent.stop()

    def test_agent_subscribe(self):

        pub = self.create_socket(zmq.PUB)
        port = pub.bind_to_random_port('tcp://127.0.0.1')
        endpoint = 'tcp://127.0.0.1:{}'.format(port)

        agent = Agent()

        topic1 = 'topic1'
        topic2 = 'topic2'

        class MemMethod(object):

            def __init__(self_):
                self_.called = 0

            def __call__(self_, sender, topic, content, msgid):
                self_.called += 1
                self.assertEqual(sender, endpoint)
                self.assertEqual(topic, topic1)
                self.assertEqual(content, 'you should know that')

        fun = MemMethod()

        prot = Protocol()
        agent.subscribe(endpoint, topic1, fun, endpoint)
        time.sleep(SLEEP_SECS)
        pub.send_multipart(prot.format(endpoint, topic1, 'you should know that'))
        time.sleep(4 * SLEEP_SECS)
        self.assertEqual(fun.called, 1)
        pub.send_multipart(prot.format(endpoint, topic2, 'you should know that'))
        time.sleep(SLEEP_SECS)
        self.assertEqual(fun.called, 1)

        agent.stop()
        pub.close()


    def test_agent_subscribe_default(self):

        pub = self.create_socket(zmq.PUB)
        port = pub.bind_to_random_port('tcp://127.0.0.1')
        endpoint = 'tcp://127.0.0.1:{}'.format(port)

        class DefNot(Agent):

            called = 0

            def on_notification(self, sender, topic, msgid, content):
                self.called += 1

        agent = DefNot()

        topic1 = 'topic1'
        topic2 = 'topic2'
        topic3 = 'topic3'

        def do_nothing(sender, topic, msgid, content):
            pass

        prot = Protocol()

        agent.subscribe(endpoint, topic1, None, endpoint)
        agent.subscribe(endpoint, topic2, do_nothing, endpoint)
        time.sleep(SLEEP_SECS)

        pub.send_multipart(prot.format(endpoint, topic1, 'some'))
        time.sleep(SLEEP_SECS)
        self.assertEqual(agent.called, 1)

        pub.send_multipart(prot.format(endpoint, topic2, 'more news'))
        time.sleep(SLEEP_SECS)
        self.assertEqual(agent.called, 1)

        pub.send_multipart(prot.format(endpoint, topic3, 'you should know that'))
        time.sleep(SLEEP_SECS)
        self.assertEqual(agent.called, 1)

        pub.close()
        agent.stop()

    def test_signal(self):

        address = 'tcp://127.0.0.1:6008'

        s = Server(Example(), rep_endpoint=address)

        proxy = Proxy(address)

        class MemMethod(object):

            def __init__(self_):
                self_.called = 0

            #def __call__(self_, value, old_value, others):
            #    self_.called += 1
            def __call__(self_, value):
                self_.called += 1

        fun1 = MemMethod()
        self.assertEqual(fun1.called, 0)
        self.assertEqual(len(s.served_object.rw_prop_changed.slots), 0)
        proxy.rw_prop_changed.connect(fun1)
        time.sleep(SLEEP_SECS)
        self.assertEqual(len(s.served_object.rw_prop_changed.slots), 1)
        proxy.rw_prop = 28
        time.sleep(SLEEP_SECS)
        self.assertEqual(proxy.rw_prop, 28)
        self.assertEqual(fun1.called, 1)  # fail?

        fun2 = MemMethod()
        self.assertEqual(fun2.called, 0)
        proxy.rw_prop_changed.connect(fun2)
        time.sleep(SLEEP_SECS)
        self.assertEqual(len(s.served_object.rw_prop_changed.slots), 1)
        proxy.rw_prop = 29
        time.sleep(SLEEP_SECS)
        self.assertEqual(proxy.rw_prop, 29)
        self.assertEqual(fun1.called, 2)
        self.assertEqual(fun2.called, 1)

        proxy.rw_prop_changed.disconnect(fun1)
        time.sleep(SLEEP_SECS)
        self.assertEqual(len(s.served_object.rw_prop_changed.slots), 1)
        proxy.rw_prop = 30
        self.assertEqual(fun1.called, 2)

        proxy.rw_prop_changed.disconnect(fun2)
        time.sleep(SLEEP_SECS)
        self.assertEqual(len(s.served_object.rw_prop_changed.slots), 0)

        proxy.rw_prop_changed.connect(fun1)
        proxy.rw_prop_changed.connect(fun2)
        time.sleep(SLEEP_SECS)
        self.assertEqual(len(s.served_object.rw_prop_changed.slots), 1)
        proxy.rw_prop_changed.disconnect(None)
        time.sleep(SLEEP_SECS)
        self.assertEqual(len(s.served_object.rw_prop_changed.slots), 0)

        proxy._proxy_stop_server()
        proxy._proxy_stop_me()

    def test_signal_two_proxies(self):

        address = 'tcp://127.0.0.1:6009'

        s = Server(Example(), rep_endpoint=address)

        proxy1 = Proxy(address)
        proxy2 = Proxy(address)

        class MemMethod(object):

            def __init__(self_):
                self_.called = 0

            #def __call__(self_, value, old_value, others):
            #    self_.called += 1
            def __call__(self_, value):
                self_.called += 1

        fun = MemMethod()

        self.assertEqual(len(s.served_object.rw_prop_changed.slots), 0)
        proxy2.rw_prop_changed.connect(fun)
        time.sleep(SLEEP_SECS)
        self.assertEqual(len(s.served_object.rw_prop_changed.slots), 1)
        proxy1.p = 28

        proxy1._proxy_stop_server()
        proxy1._proxy_stop_me()
        proxy2._proxy_stop_me()

    def test_future(self):

        s = Server(Example())

        proxy = Proxy(s.rep_endpoint)

        fut = proxy.fut()
        self.assertEqual(fut.result(), 10)

        fut = proxy.fut_raise()
        self.assertIsInstance(fut.exception(), ValueError)

        fut = proxy.fut_raise()
        self.assertRaises(ValueError, fut.result)

        proxy._proxy_stop_me()
        s.stop()

if __name__ == '__main__':
    unittest.main()
