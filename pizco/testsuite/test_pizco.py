# -*- coding: utf-8 -*-

import time
import operator
import threading

from threading import Thread

from concurrent.futures import ThreadPoolExecutor
import zmq

from pizco.compat import Queue, Empty

def set_zmq_context_to_none():
    if hasattr(zmq.Context, '_instance'):
        zmq.Context._instance = None
    else:
        zmq.context._instance = None

from pizco import Proxy, Server, Agent, Signal
from pizco.protocol import Protocol
from pizco.compat import unittest, PYTHON3


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

class ExampleAuto(object):

    def __init__(self):
        from pizco import Signal
        Signal = Signal.Auto
        self.simple_attribute = 12
        self._private_value = 42
        self.dict_attribute = {1: 2}

        self._rw_prop = 42
        self._ro_prop = 42
        self._wo_prop = 42
        self.rw_prop_changed = Signal()
        self.wo_prop_changed = Signal()


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


        
import random
class RandomTestData(object):
    def __init__(self,size=1024):
        random.seed()
        self.rand = random.sample(range(0,10000000), size)
    def __repr__(self):
        return str(self.rand[0:5])[:-1]+'...'+str(self.rand[-5:])[1:]


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

    @unittest.skip('This test halts when executed with others')
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
        endpoint = 'tcp://127.0.0.1:{0}'.format(port)

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
        endpoint = 'tcp://127.0.0.1:{0}'.format(port)

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
        
    def test_signal_auto(self):

        address = 'tcp://127.0.0.1:6008'

        s = Server(ExampleAuto(), rep_endpoint=address)

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
        
    def test_wildcards(self):
        from threading import Thread,Event
        from functools import partial
        class AggressiveServerObject(Thread):
            sig_aggressive = Signal(2)
            signal_size = 1024
            signal_number = 100
            def __init__(self):
                super(AggressiveServerObject,self).__init__(name="PeerWatcher")
                self._exit_e = Event()
                self._job_e = Event()
                self._job_e.set()
                self._events = Queue()
                self._periodicity = 0.01
                self.heartbeat = 0
                self._signal_sent = 0
                self.add_events()

            def add_events(self):
                for i in range(0,self.signal_number):
                    self.generate_random()
            def run(self):
                while not self._exit_e.isSet():
                    if self._job_e.isSet():
                        start_time = time.time()
                        self.heartbeat += 1
                        self.process_queue()
                        exec_time = time.time()-start_time
                    if self._exit_e.wait(self._periodicity-exec_time):
                        break
            def process_queue(self):
                if self.is_alive():
                    try:
                        event = self._events.get(timeout=1)
                    except Empty:
                        pass
                    else:
                        event()
            def generate_random(self):
                evtcbk = partial(self.delayed_random,signal=RandomTestData(),num=self._signal_sent)
                self._events.put(evtcbk)
            def delayed_random(self,signal,num):
                self.sig_aggressive.emit(signal,num)
                self._signal_sent += 1
            def pause(self):
                self._job_e.clear()
            def unpause(self):
                self._job_e.set()
            def stop(self):
                self._job_e.clear()
                self._exit_e.set()
                self.join()#self._periodicity*3

        class AggressiveClientObject(object):
            def __init__(self):
                super(AggressiveClientObject,self).__init__()
                self.received = 0
            def slot_aggressive(self, randstuff, sigcount):
                self.received += 1
                sigcount = sigcount
                randstuff = randstuff
        
        def get_local_ip():
            import socket
            addrList = socket.getaddrinfo(socket.gethostname(), None)
            ipList=[]
            for item in addrList:
                if item[0] == 2:
                    ipList.append(item[4][0])
            return ipList
            
        endpoint = "tcp://*:8200"
        endpoint1 = "tcp://127.0.0.1:8200"
        endpoint2 = "tcp://"+get_local_ip()[0]+":8200"
        serverto = AggressiveServerObject()
        server = Server(serverto, rep_endpoint=endpoint)
        serverto.add_events()
        to = AggressiveClientObject()
        i = Proxy(endpoint1)
        i.sig_aggressive.connect(to.slot_aggressive)
        serverto.start()
        serverto.add_events()
        time.sleep(1.5)
        self.assertNotEqual(to.received,0)
        i.pause()
        beat_before = i.heartbeat
        time.sleep(0.5)
        beat_after_pause = i.heartbeat
        i.unpause()
        time.sleep(0.5)
        beat_after_unpause = i.heartbeat
        self.assertGreater(beat_before,0)
        self.assertEqual(beat_before,beat_after_pause,1)
        self.assertGreater(beat_after_unpause,beat_after_pause)
        i._proxy_stop_me()
        del i # necessary to perform post stop callbacks

        to2 = AggressiveClientObject()
        i2 = Proxy(endpoint2)
        i2._proxy_ping()
        i2.sig_aggressive.connect(to2.slot_aggressive)
        serverto.add_events()
        time.sleep(0.5)
        i2.pause()
        beat_before = i2.heartbeat
        time.sleep(0.5)
        beat_after_pause = i2.heartbeat
        i2.unpause()
        time.sleep(0.5)
        beat_after_unpause = i2.heartbeat
        self.assertGreater(beat_before,0)
        self.assertEqual(beat_before,beat_after_pause,1)
        self.assertGreater(beat_after_unpause,beat_after_pause)
        i2._proxy_stop_me()
        del i2 # necessary to avoid post stop callbacks
        serverto.stop()
        server.stop()
        time.sleep(5)
    def test_proxy_and_server_pickling(self):
        import pickle
        s = Server(Example())
        x = pickle.dumps(s)
        print x
        px = pickle.loads(x)
        print type(px)
        fut = px.fut()
        self.assertEqual(fut.result(), 10)
        xp = pickle.dumps(px)
        print xp
        pp = pickle.loads(xp)
        fut2 = pp.fut()
        self.assertEqual(fut2.result(), 10)
        pp._proxy_stop_me()
        px._proxy_stop_me()
        s.stop()
        s.wait_stop()


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(AgentTest)
    unittest.TextTestRunner(verbosity=100).run(suite)
