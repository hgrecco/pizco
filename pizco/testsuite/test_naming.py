# -*- coding: utf-8 -*-

import time
import random
import logging
from multiprocessing import freeze_support
from functools import partial

from threading import Thread, Event

from pizco import Signal, LOGGER, Proxy, Server
from pizco.naming import PeerWatcher, ServicesWatcher, Naming
from pizco.compat import Queue, Empty, PYTHON3, u, unittest


def configure_test(level, process):
    global perform_test_in_process
    global test_log_level
    test_log_level = level
    perform_test_in_process = process

configure_test(logging.DEBUG,False)


class TestObject(object):
    def __init__(self):
        self._times = 1
    def times(self,multiply):
        self._times *= multiply
        return self._times


class NamingTestObject(object):
    sig_register_local_service = Signal(2)
    sig_unregister_local_service = Signal(1)
    def on_service_death(self,service):
        LOGGER.info(service + " is dead")
        self.service = service


perform_test_in_process = False
test_log_level = logging.DEBUG


class AggressiveTestServerObject(Thread):
    sig_aggressive = Signal(2)
    signal_size = 1024
    signal_number = 100

    def __init__(self):
        super(AggressiveTestServerObject,self).__init__(name="PeerWatcher")
        self._exit_e = Event()
        self._job_e = Event()
        self._job_e.set()
        self._events = Queue()
        self._periodicity = 0.1
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
                #print("heartbeat {}".format(self.heartbeat))
                self.process_queue()
                exec_time = time.time() - start_time
            if self._exit_e.wait(self._periodicity - exec_time):
                break

    def process_queue(self):
        if self.is_alive():
            try:
                event = self._events.get(timeout=0.1)
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
        self.join()  # self._periodicity*3


class AggressiveTestClientObject(object):

    def __init__(self):
        super(AggressiveTestClientObject,self).__init__()
        self.received = 0

    def slot_aggressive(self, randstuff, sigcount):
        self.received += 1
        sigcount = sigcount
        randstuff = randstuff
        LOGGER.debug("slot match")


class RandomTestData(object):

    def __init__(self,size=1024):
        random.seed()
        if PYTHON3:
            self.rand = random.sample(range(10000000), size)
        else:
            self.rand = random.sample(xrange(10000000), size)

    def __repr__(self):
        return str(self.rand[0:5])+'...'+str(self.rand[-5:])



class TestNamingService(unittest.TestCase):
    def testPeerWatcher(self):
        LOGGER.setLevel(test_log_level)

        while PeerWatcher.check_beacon_port():
            print("Suspecting naming service to be running")
            LOGGER.info("trying to stop naming service")
            ns = Naming.start_naming_service(in_process=perform_test_in_process)
            ns._proxy_stop_server()
            del ns
            time.sleep(1)
        pw = PeerWatcher()
        pw.start()
        print(pw.peers_list)
        pw.sig_peer_event.disconnect()
        time.sleep(3)
        print(pw.peers_list)
        pw.stop()
        del pw

    def testServiceWatcher(self):
        LOGGER.setLevel(test_log_level)
        while PeerWatcher.check_beacon_port():
            print ("checking beacon port saying it's not free")
            LOGGER.info("trying to stop naming service")
            ns = Naming.start_naming_service(in_process=perform_test_in_process)
            ns._proxy_stop_server()
            del ns
            time.sleep(2)
        #watch for non responding services
        sw = ServicesWatcher()
        ns = NamingTestObject()
        sw.sig_service_death.connect(ns.on_service_death)
        ns.sig_register_local_service.connect(sw.register_local_proxy)
        ns.sig_unregister_local_service.connect(sw.unregister_local_proxy)
        sw.start()

        to = TestObject()
        s = Server(to,rep_endpoint="tcp://*:6500")
        ns.sig_register_local_service.emit("myremote","tcp://*:6500")

        LOGGER.info(sw._local_services)
        time.sleep(2)
        s.stop()
        s.wait_stop(timeout=None)
        del s
        time.sleep(2)
        LOGGER.info(sw._local_services)
        sw.stop()
        del sw
        time.sleep(2)
        ns.sig_unregister_local_service.emit("myremote")
        del ns

    def testNormalCaseServiceDeath(self):
        Naming.set_ignore_local_ip(True)
        LOGGER.setLevel(test_log_level)
        ns = Naming.start_naming_service(in_process=perform_test_in_process)
        self.assertNotEqual(ns, None)
        time.sleep(1)
        #local_pxy = Proxy("tcp://127.0.0.1:5777",300)
        to = TestObject()
        s = Server(to,rep_endpoint="tcp://*:6500")
        ns.register_local_service("myremote", "tcp://*:6500")
        time.sleep(0.5)
        x = ns.get_endpoint("myremote")
        ns.test__peer_death()
        self.assertEqual(ns.get_services(),
                         {'myremote': 'tcp://127.0.0.1:6500',
                          'pizconaming': 'tcp://127.0.0.1:5777'})
        time.sleep(PeerWatcher.PING_INTERVAL*(PeerWatcher.LIFE_INTERVAL+0.5)*PeerWatcher.PEER_LIFES_AT_START)
        LOGGER.info("simulation of server object crash")
        ns.test__peer_death_end()
        x = ns.get_endpoint("myremote")
        addproxy = Proxy(x,creation_timeout=3000)
        addproxy._proxy_stop_server()
        del addproxy
        time.sleep(PeerWatcher.PING_INTERVAL*(PeerWatcher.LIFE_INTERVAL+5)) #ping standard time
        self.assertEqual(ns.get_services(), {'pizconaming': 'tcp://127.0.0.1:5777'})
        time.sleep(1)
        ns._proxy_stop_server()
        ns._proxy_stop_me()
        s.stop()
        s.wait_stop(timeout=None)
        del ns

    def testNormalCase(self):
        LOGGER.setLevel(test_log_level)
        ns = Naming.start_naming_service(in_process=perform_test_in_process)
        self.assertNotEqual(ns, None)
        to = TestObject()
        s = Server(to,rep_endpoint="tcp://*:6500")
        ns.register_local_service("myremote","tcp://*:6500")
        addproxy = Proxy(ns.get_endpoint("myremote"))
        self.assertEqual(addproxy.times(50),50)
        time.sleep(1)
        LOGGER.info(ns.get_services())
        self.assertEqual(ns.get_services(),
                         {'myremote': 'tcp://127.0.0.1:6500',
                          'pizconaming': 'tcp://127.0.0.1:5777'})
        time.sleep(1)
        addproxy._proxy_stop_server()
        del addproxy
        ns._proxy_stop_server()
        ns._proxy_stop_me()

        del ns


    def testARemoteCase(self):
        import logging
        logging.getLogger().setLevel(logging.DEBUG)
        LOGGER.setLevel(test_log_level)
        ##optionnally start in separate thread
        endpoint = "tcp://127.0.0.1:8000"
        endpoint1 = "tcp://127.0.0.1:8001"
        serverto = AggressiveTestServerObject()
        s = Server(serverto,rep_endpoint=endpoint)
        #s = Server.serve_in_thread(AggressiveTestServerObject,(),{},rep_endpoint=endpoint)
        ns = Naming.start_naming_service(in_process=perform_test_in_process)
        ns.register_local_service("aggressive", endpoint)
        time.sleep(2)
        to = AggressiveTestClientObject()
        time.sleep(1)
        LOGGER.info(ns.get_services())
        endpoint1 = u(ns.get_endpoint("aggressive"))
        self.assertNotEqual(endpoint1,None)
        LOGGER.info(endpoint1)
        i = Proxy(endpoint1)
        time.sleep(1)
        i.sig_aggressive.connect(to.slot_aggressive)
        time.sleep(1)
        serverto.start()
        serverto.unpause()
        time.sleep(5)
        i.pause()
        LOGGER.info('heartbeat = %s', i.heartbeat)
        beat_before = i.heartbeat
        dir(i.heartbeat)
        time.sleep(1)
        LOGGER.info('heartbeat = %s', i.heartbeat)
        beat_after_pause = i.heartbeat
        i.unpause()
        time.sleep(2)
        beat_after_unpause = i.heartbeat
        LOGGER.info('heartbeat = %s', i.heartbeat)
        self.assertGreater(beat_before, 0)
        self.assertEqual(beat_before, beat_after_pause, 1)
        self.assertGreater(beat_after_unpause, beat_after_pause)
        self.assertNotEqual(to.received, 0)
        print("done ar with ns")
        i.sig_aggressive.disconnect(to.slot_aggressive)
        ns.unregister_local_service("aggressive")
        i._proxy_stop_server()
        i._proxy_stop_me()
        del i
        serverto.stop()
        s.stop()
        s.wait_stop(timeout=None)
        ns._proxy_stop_server()
        ns._proxy_stop_me()
        del ns

    def testARemoteCaseMulti(self):
        #endpoint = "ipc://robbie-the-robot" not supported in windows
        LOGGER.setLevel(test_log_level)
        endpoint = "tcp://*:8100"
        endpoint1 = "tcp://127.0.0.1:8100"
        endpoint2 = "tcp://" + Naming.get_local_ip()[0] + ":8100"
        serverto = AggressiveTestServerObject()
        ns = Naming.start_naming_service(in_process=perform_test_in_process)
        server = Server(serverto, rep_endpoint=endpoint)
        ns.register_local_service("aggressive2",endpoint)

        serverto.add_events()

        to = AggressiveTestClientObject()
        i = Proxy(endpoint1)
        i.sig_aggressive.connect(to.slot_aggressive)
        serverto.start()
        serverto.add_events()

        time.sleep(2)
        LOGGER.debug('X frame received %s', to.received)
        self.assertNotEqual(to.received,0)
        i.pause()
        LOGGER.info('heartbeat = %s', i.heartbeat)
        beat_before = i.heartbeat
        time.sleep(0.5)
        LOGGER.info('heartbeat = %s', i.heartbeat)
        beat_after_pause = i.heartbeat
        i.unpause()
        time.sleep(0.5)
        beat_after_unpause = i.heartbeat
        LOGGER.info('heartbeat = %s', i.heartbeat)
        self.assertGreater(beat_before, 0)
        self.assertEqual(beat_before, beat_after_pause, 1)
        self.assertGreater(beat_after_unpause, beat_after_pause)
        i._proxy_stop_me()
        del i # necessary to perform post stop callbacks

        LOGGER.info("attacking secondary object")
        to2 = AggressiveTestClientObject()
        i2 = Proxy(endpoint2)
        i2._proxy_ping()
        i2.sig_aggressive.connect(to2.slot_aggressive)
        serverto.add_events()
        time.sleep(0.5)
        i2.pause()
        LOGGER.info('heartbeat = %s', i2.heartbeat)
        beat_before = i2.heartbeat
        time.sleep(0.5)
        LOGGER.info('heartbeat = %s', i2.heartbeat)
        beat_after_pause = i2.heartbeat
        i2.unpause()
        time.sleep(0.5)
        beat_after_unpause = i2.heartbeat
        LOGGER.info('heartbeat = %s', i2.heartbeat)
        self.assertGreater(beat_before,0)
        self.assertEqual(beat_before,beat_after_pause,1)
        self.assertGreater(beat_after_unpause,beat_after_pause)
        LOGGER.info("quitting secondary object")
        i2._proxy_stop_me()
        ns.unregister_local_service("aggressive2")

        del i2 # necessary to avoid post stop callbacks
        serverto.stop()
        server.stop()
        ns._proxy_stop_server()
        ns._proxy_stop_me()
        del ns
    def testBasicStartStopStart(self):
        LOGGER.setLevel(test_log_level)
        from pizco import Agent
        Agent.set_default_ioloop("new")
        ns = Naming.start_naming_service(in_process=False)
        to = TestObject()
        for i in range(0,5):
            print("---#####TEST####---")
            #s = Server(to,rep_endpoint="tcp://*:6500")
            s = Server.serve_in_thread(TestObject,(),{},rep_endpoint="tcp://*:6500")
            #s = Server.serve_in_process(TestObject,(),{},rep_endpoint="tcp://*:6500")
            print("registering service")
            pxy = Proxy("tcp://127.0.0.1:6500")
            print(pxy)
            ns.register_local_service("myremote", "tcp://*:6500")
            print(ns.get_services())
            print("reading endpoint")
            print(ns.get_endpoint("myremote"))
            time.sleep(0.5)
            print("stopping server")
            self.assertTrue("myremote" in ns.get_services())
            print("waiting")
            #s.stop()
            #s.wait_stop()
            s._proxy_stop_server()
            #s._proxy_wait_stop(timeout=0)
            time.sleep(7)
            print("trying to read services")
            print(ns.get_services())
            no_more_my_remote = not "myremote" in ns.get_services()
            self.assertTrue(no_more_my_remote)
            print("restarting loop")
        ns._proxy_stop_server()
        assert(not PeerWatcher.check_beacon_port())


if __name__ == "__main__":
    #import multiprocessing as mp
    #mp.log_to_stderr(logging.DEBUG)
    #mp.get_logger().setLevel(logging.DEBUG)
    Naming.set_ignore_local_ip(True)
    Server.set_default_ioloop("new")
    Naming.set_service_watcher_method("socket")

    print("config 1., separate loop's threads")
    configure_test(logging.WARNING,False)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestNamingService)
    unittest.TextTestRunner(verbosity=2).run(suite)
    print("config 1b., running in process")
    configure_test(logging.WARNING,True)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestNamingService)
    unittest.TextTestRunner(verbosity=2).run(suite)
    
    Server.set_default_ioloop("instance")
    print("config 2, single loop instance threads")
    
    print("config 2b., running in process")
    configure_test(logging.WARNING,False)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestNamingService)
    unittest.TextTestRunner(verbosity=2).run(suite)

    print("config 2b., running in process")
    configure_test(logging.WARNING,True)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestNamingService)
    unittest.TextTestRunner(verbosity=2).run(suite)

    print("config 3. Pizco type watchdog")
    
    Naming.set_ignore_local_ip(False)
    Naming.set_service_watcher_method("pizco")
    Server.set_default_ioloop("new")
    
    print("config 3., service watcher : PIZCO PROXY")
    configure_test(logging.WARNING,False)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestNamingService)
    unittest.TextTestRunner(verbosity=2).run(suite)
    
    print("config 3b., service watcher : PIZCO PROXY in PROCESS")
    configure_test(logging.WARNING,True)
    suite = unittest.TestLoader().loadTestsFromTestCase(TestNamingService)
    unittest.TextTestRunner(verbosity=2).run(suite)

