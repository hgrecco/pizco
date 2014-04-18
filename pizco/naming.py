#!/usr/bin/env python
# -*- coding: utf-8 -*-
""" helpers.py : common utilities functions used in project """
__author__ = "SVNUSER"
__status__ = "Prototype" #Prototype #Developpement

#
# UDP ping command
# Model 1
#

import os
import socket
import sys
import time
import zmq

__all__ = ["Naming"]

from threading import Lock, Thread, Timer, Event
from . import Server, Signal, Proxy, LOGGER
from timeit import timeit
from Queue import Queue, Empty
from functools import partial
from multiprocessing import freeze_support

class PeerWatcher(Thread):
    PING_PORT_NUMBER = 9999
    PING_MSG_SIZE = 1
    PING_INTERVAL = 1 # Once per second
    LIFE_INTERVAL = 3
    PEER_LIFES_AT_START = 5

    sig_peer_event = Signal()
    sig_peer_birth = Signal()
    sig_peer_death = Signal()

    def __init__(self,local_only=False):
        super(PeerWatcher,self).__init__(name="PeerWatcher")
        self._exit_e = Event()
        self._job_e = Event()
        self._job_e.set()
        self._events = Queue(30)

        self._periodicity = 0.2
        self._heartbeat = 0
        self.peers_list = {}
        self.sig_peer_event.connect(self.on_peer_event)

        if local_only:
            self._job_e.clear()
            self._exit_e.clear()
            
    def run(self):
        self._init_beacon()
        while not self._exit_e.isSet():
            if self._job_e.isSet():
                start_time = time.time()
                self.do_job()
                self.process_queue()
                exec_time = time.time()-start_time
            if self._exit_e.wait(self._periodicity-exec_time):
                break
        self.sig_peer_event.disconnect()
        self._end_beacon()
    def process_queue(self):
        if self.is_alive():
            try:
                event = self._events.get(timeout=1)
            except Empty:
                pass
            else:
                event()
    def do_job(self):
        self._heartbeat+=1
        self._beacon_receive_job()
        if (self._heartbeat*self._periodicity%self.PING_INTERVAL) < self._periodicity:
            self._beacon_send_job()
        if (self._heartbeat*self._periodicity%self.LIFE_INTERVAL) < self._periodicity:
            self._life_job()

    def stop(self):
        LOGGER.debug("stopping peer watcher")
        self._job_e.clear()
        self._exit_e.set()
        self.join()#self._periodicity*3
        LOGGER.debug("done stopping peers watcher")

    def _init_beacon(self):
        # Create UDP socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        # Ask operating system to let us do broadcasts from socket
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        # Bind UDP socket to local port so we can receive pings
        sock.bind(('', self.PING_PORT_NUMBER))

        # We use zmq_poll to wait for activity on the UDP socket, since
        # this function works on non-0MQ file handles. We send a beacon
        # once a second, and we collect and report beacons that come in
        # from other nodes:

        poller = zmq.Poller()
        poller.register(sock, zmq.POLLIN)
        self._sock = sock
        self._poller = poller
        self.ping_at = time.time()
        LOGGER.debug("ping watcher started")
    
    def _end_beacon(self):
        if hasattr(self,"_sock"):
            self._sock.close()
            del self._sock
            del self._poller

    def __del__(self):
        self.stop()

    def _beacon_receive_job(self):
        #dure au moins 1 seconde si des reponses dure moins de temps
        #LOGGER.debug("polling events for half periodicity")
        events = dict(self._poller.poll(self._periodicity*100/2))
        # Someone answered our ping
        if self._sock.fileno() in events:
            msg, addrinfo = self._sock.recvfrom(self.PING_MSG_SIZE)
            LOGGER.debug("Found peer %s:%d" % addrinfo)
            self.sig_peer_event.emit(addrinfo[0])

    def _beacon_send_job(self):
        #LOGGER.debug(("Pinging peers…"))
        self._sock.sendto(b'!', 0, ("255.255.255.255", self.PING_PORT_NUMBER))
        self.ping_at = time.time() + self.PING_INTERVAL
        #LOGGER.debug(time.time())

    def _life_job(self):
        death_list = []
        for k,v in self.peers_list.iteritems():
            if v > 0:
                self.peers_list[k] = v-1
                if v >= self.PEER_LIFES_AT_START:
                    LOGGER.debug("promoted {} score {}".format(k,v))
                    self.sig_peer_birth.emit(unicode(k))
            else:
                LOGGER.debug("death of peer {}".format(k))
                death_list.append(k)
                self.sig_peer_death.emit(unicode(k))
        for k in death_list:
            self.peers_list.pop(k)

    def on_peer_event(self,addrinfo):
        evt=partial(self.delayed_peer_event,addrinfo=addrinfo)
        self._events.put(evt)
        
    def delayed_peer_event(self,addrinfo):
        LOGGER.debug(self.peers_list)
        if self.peers_list.has_key(addrinfo):
            if self.peers_list[addrinfo] < self.PEER_LIFES_AT_START:
                self.peers_list[addrinfo] += 1
        else:
            self.peers_list[addrinfo] = self.PEER_LIFES_AT_START

    @staticmethod
    def check_beacon_port(localonly=False):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
            # Ask operating system to let us do broadcasts from socket
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            # Bind UDP socket to local port so we can receive pings
            if localonly:
                address = '127.0.0.1'
            else:
                address = ''
            sock.bind((address, PeerWatcher.PING_PORT_NUMBER))
        except Exception as e:
            if len(e.args) and e.args[0] == 10048:
                return True
            else:
                LOGGER.error("exception in socket verification")
                sock = None
                return False
                raise e
        else:
            sock.close()
            sock = None
            return False
        return False


class ServicesWatcher(Thread):
    CHECK_INTERVAL = 5
    sig_service_death = Signal()
    def __init__(self):
        super(ServicesWatcher,self).__init__(name="ServicesWatcher")
        self._exit_e = Event()
        self._job_e = Event()
        self._job_e.set()
        self._events = Queue(30)
        self._periodicity = 3
        self._heartbeat = 0
        self._local_proxies = {}
        self._sl_lock = Lock()
        LOGGER.debug("service watcher started")
    def __del__(self):
        self.stop()
        
    def run(self):
        print "starting run"
        exec_time = 0
        while not self._exit_e.isSet():
            if self._job_e.isSet():
                start_time = time.time()
                self.do_job()
                self.process_queue()
                exec_time = time.time()-start_time
            if self._exit_e.wait(self._periodicity-exec_time):
                break
        self.end_watch()
        print "end main loop"
    def end_watch(self):
        pass
        #for k,v in self._local_proxies.iteritems():
        #   v._proxy_stop_me()
                
    def do_job(self):
        self._heartbeat+=1
        self._local_services_ping_job()

    def process_queue(self):
        if self.is_alive():
            try:
                event = self._events.get(timeout=1)
            except Empty:
                pass
            else:
                event()
    def stop(self):
        LOGGER.debug("stopping service watcher")
        self.sig_service_death.disconnect()
        self._job_e.clear()
        self._exit_e.set()
        self.join() # wont work if peer periodicity is self._periodicity*5
        LOGGER.debug("done stopping service watcher")


    def register_local_proxy(self,servicename, endpoint):
        LOGGER.debug("register proxy in event loop")
        evtcbck = partial(self.delayed_register_local_proxy,servicename=servicename,endpoint=endpoint)
        self._events.put(evtcbck)
        
    def delayed_register_local_proxy(self,servicename,endpoint):
        LOGGER.debug(("registering local proxy",servicename,endpoint))
        endpoint = endpoint.replace("*","127.0.0.1")
        with self._sl_lock:
            if servicename not in self._local_proxies:
                try:
                    self._local_proxies[servicename] = Proxy(endpoint,2000)
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    LOGGER.error(("registering local proxy",servicename,endpoint))
            LOGGER.debug(self._local_proxies)

    def _local_services_ping_job(self):
        death_list = []
        with self._sl_lock:
            for k,v in self._local_proxies.iteritems():
                start_time = time.time()
                retcode = v._proxy_ping(3000)
                LOGGER.debug(("ping duration ", time.time() - start_time))
                LOGGER.debug(("pinging server ",k,retcode))
                if retcode == u"ping":
                    pass
                else:
                    death_list.append(k)
        for service in death_list:
            self.unregister_local_proxy(service)
            self.sig_service_death.emit(service)
            
    def unregister_local_proxy(self,service_name):
        with self._sl_lock:
            #self._local_proxies[service_name]._proxy_stop_me()
            self._local_proxies.pop(service_name)


class Naming(Thread):
    NAMING_SERVICE_PORT = 5777

    sig_remote_services = Signal()
    sig_register_local_service = Signal()
    sig_unregister_local_service = Signal()

    sig_exportable_services = Signal()

    def __init__(self,local_only=False, parent=None):
        super(Naming,self).__init__(name="NamingMain")
        self.daemon = True
        self._exit_e = Event()
        self._job_e = Event()
        self._job_e.set()
        self._events = Queue(30)

        self._periodicity = 100
        self.peer_proxies = {}
        self.peer_slots = {}
        self.peers_services = {}
        self.local_services = {}
        self.exportable_local_services = {}
        self.remote_services = {}

        self._local_ip = self.get_local_ip()

        self._serviceslock = Lock()
        self._socketlock = Lock()
        self.sig_remote_services.connect(self._on_remote_services)

        #watch for peers in the neighboorhood responding to ping and having a naming service
        self._pwatcher = PeerWatcher(local_only)
        self._pwatcher.sig_peer_birth.connect(self.on_peer_birth)
        self._pwatcher.sig_peer_death.connect(self.on_peer_death)
        self._pwatcher.start()

        #watch for non responding services
        self._swatcher = ServicesWatcher()
        self._swatcher.sig_service_death.connect(self.on_service_death)
        self.sig_register_local_service.connect(self._swatcher.register_local_proxy)
        self.sig_unregister_local_service.connect(self._swatcher.unregister_local_proxy)
        self._swatcher.start()


    def run(self):
        while not self._exit_e.isSet():
            if self._job_e.isSet():
                start_time = time.time()
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

    def get_local_ip(self):
        addrList = socket.getaddrinfo(socket.gethostname(), None)
        ipList=[]
        for item in addrList:
            if item[0] == 2:
                ipList.append(item[4][0])
        return ipList


    def stop(self):
        LOGGER.debug("stopping naming main")
        self._job_e.clear()
        self._exit_e.set()
        self.join()
        LOGGER.debug("stopped naming main")
        self._swatcher.stop()
        self._pwatcher.stop()
        
    def __del__(self):
        self.stop()

    @staticmethod
    def start_naming_service(in_process=True, local_only=False):
        if PeerWatcher.check_beacon_port(local_only) == False:
            if local_only:
                address = "127.0.0.1"
            else:
                address = "*"
            if in_process:
                LOGGER.info("starting server in a remote process")
                pxy = Server.serve_in_process(Naming, args=(local_only,),kwargs={}, rep_endpoint="tcp://"+address+":"+str(Naming.NAMING_SERVICE_PORT))
            else:
                LOGGER.info("starting server in a thread")
                pxy = Server.serve_in_thread(Naming, args=(local_only,),kwargs={}, rep_endpoint="tcp://"+address+":"+str(Naming.NAMING_SERVICE_PORT))
            pxy.start()                
            pxy.register_local_service("pizconaming","tcp://"+address+":"+str(Naming.NAMING_SERVICE_PORT))
        else:
            try:
                pxy = Proxy("tcp://127.0.0.1:"+str(Naming.NAMING_SERVICE_PORT),3000)
                try:
                    pxy.get_services()
                except:
                    pxy._proxy_stop_server()
                    return None
            except Exception as e:
                if e.args[0] == "Timeout":
                    LOGGER.error("check hidden python processes")
                    return None
                else:
                    import traceback
                    traceback.print_exc()
                    raise e
        return pxy
    def on_peer_death(self, addrinfo):
        with self._serviceslock:
            death_list = []
            for name, endpoint in self.remote_services.iteritems():
                if endpoint.find(addrinfo) != -1:
                    death_list.append(name)
            for remote in death_list:
                self.remote_services.pop(remote)
        if self.peer_proxies.has_key(addrinfo):
            self.peer_proxies.pop(addrinfo)
            

    def _make_remote_services_slot(self,addrinfo):
        def remote_services_slot(type, services):
            address = addrinfo
            self._on_remote_services(address, type, services)
        return remote_services_slot

    def on_peer_birth(self,addrinfo):
        import functools
        if not self.peer_proxies.has_key(addrinfo):
            LOGGER.debug(addrinfo)
            try:
                rn_service = Proxy("tcp://{}:{}".format(addrinfo,self.NAMING_SERVICE_PORT),creation_timeout=2000)
            except:
                LOGGER.error("no naming service present at ",addrinfo, self.NAMING_SERVICE_PORT)
            else:
                self.peer_proxies[addrinfo] = rn_service
                custom_slot = self._make_remote_services_slot(addrinfo)
                try:
                    services = rn_service.get_exportable_services()
                    self._on_remote_services(addrinfo,"birth",services)
                    rn_service.sig_exportable_services.connect(custom_slot)
                except:
                    import traceback
                    traceback.print_exc()
                    


    def _on_remote_services(self, addrinfo, type, rservices):
        with self._serviceslock:
            if type == "birth":
                for name,port in rservices.iteritems():
                    self.remote_services[name]=  "tcp://{}:{}".format(addrinfo,port.split(":")[-1])
            elif type == "death":
                for name,port in rservices.iteritems():
                    if self.remote_services.has_key(name):
                        self.remote_services.pop(name)
            
            
    def get_endpoint(self,servicename):
        slist = self.get_services()
        if servicename in slist:
            return slist[servicename]
        else:
            return None

    def get_remote_services(self):
        with self._serviceslock:
            return self.remote_services

    def get_services(self):
        #merge dict, keep only local services if names the same way
        with self._serviceslock:
            z = self.remote_services.copy()
            z.update(self.local_services)
            return z

    def get_exportable_services(self):
        return self.exportable_local_services

    def register_local_service(self,service_name,endpoint):
        with self._serviceslock:
            try:
                LOGGER.info(("registering endpoint ",endpoint))
                #ok only if the service is the local service not the proxy
                if endpoint.find("*") != -1:
                    endpoint = endpoint.replace("*","127.0.0.1")
                    self.local_services[service_name] = endpoint
                    if service_name != "pizconaming":
                        self.exportable_local_services[service_name] = endpoint
                        self.sig_exportable_services.emit("birth",self.exportable_local_services.copy())
                elif endpoint.find("127.0.0.1") == -1:
                    #remote only managed service
                    self.exportable_local_services[service_name] = endpoint
                    if service_name != "pizconaming":
                        self.sig_exportable_services.emit("birth",self.exportable_local_services.copy())
                else:
                    self.local_services[service_name] = endpoint
                if service_name != "pizconaming":
                    self.sig_register_local_service.emit(service_name, endpoint)
            except:
                import traceback
                traceback.print_exc()
                LOGGER.error("cannot add service")

    def unregister_local_service(self,service_name):
        with self._serviceslock:
            self._sig_unregister_local_service.emit(service_name)

    def on_service_death(self,service_name):
        if self.local_services.has_key(service_name):
            self.local_services.pop(service_name)
        if self.exportable_local_services.has_key(service_name):
            self.exportable_local_services.pop(service_name)
            self.sig_exportable_services.emit("death",{service_name:"now dead"})
        #remote local has the service name
        if self.remote_services.has_key(service_name):
            self.remote_services.pop(service_name)
        
    def test_peer_death(self):
        self._pwatcher.sig_peer_event.disconnect()
        
    def test_peer_death_end(self):
        self._pwatcher.sig_peer_event.connect(self._pwatcher.on_peer_event)


class TestObject(object):
    def __init__(self):
        self._times = 1
    def times(self,multiply):
        self._times *= multiply
        return self._times

class NamingTestObject(object):
    sig_register_local_service = Signal()
    sig_unregister_local_service = Signal()
    def on_service_death(self,service):
        print service + "is dead"
        self.service = service



import unittest
import logging
perform_test_in_process = False
test_log_level = logging.DEBUG

class TestNamingService(unittest.TestCase):
    def testPeerWatcher(self):
        print "##############PEER WATCHER CLASS TEST###############"
        print "##"
        LOGGER.setLevel(logging.DEBUG)
        if PeerWatcher.check_beacon_port() == True:
            print "trying to stop naming service"
            ns = Naming.start_naming_service(in_process=perform_test_in_process)
            ns._proxy_stop_server()
            time.sleep(1)
            print PeerWatcher.check_beacon_port()
        pw = PeerWatcher()
        pw.start()
        print pw.peers_list
        pw.sig_peer_event.disconnect()
        time.sleep(2.5)
        print pw.peers_list
        pw.stop()
        del pw
        time.sleep(2.5)
        
    def testServiceWatcher(self):
        print "##############SERVICE WATCHER CLASS TEST###############"
        print "##"
        LOGGER.setLevel(test_log_level)
        if PeerWatcher.check_beacon_port() == True:
            print "trying to stop naming service"
            ns = Naming.start_naming_service(in_process=perform_test_in_process)
            ns._proxy_stop_server()
            time.sleep(1)
            print PeerWatcher.check_beacon_port()            
        #watch for non responding services
        sw = ServicesWatcher()
        ns = NamingTestObject()
        sw.sig_service_death.connect(ns.on_service_death)
        ns.sig_register_local_service.connect(sw.register_local_proxy)
        ns.sig_unregister_local_service.connect(sw.unregister_local_proxy)
        sw.start()
        to = TestObject()
        s = Server(to,rep_endpoint="tcp://*:500")
        time.sleep(4)
        ns.sig_register_local_service.emit("myremote","tcp://*:500")
        print sw._local_proxies
        time.sleep(5)
        s.stop()
        time.sleep(5)
        print sw._local_proxies
        sw.stop()
        del sw
        time.sleep(2.5)
        
    def testNormalCaseServiceDeath(self):
        print "##############NORMAL CASE SERVICE DEATH TEST###############"
        print "##"    
        LOGGER.setLevel(test_log_level)
        ns = Naming.start_naming_service(in_process=perform_test_in_process)
        self.assertNotEqual(ns, None)
        time.sleep(1)
        #local_pxy = Proxy("tcp://127.0.0.1:5777",300)
        to = TestObject()
        s = Server(to,rep_endpoint="tcp://*:500")
        time.sleep(1)
        ns.register_local_service("myremote","tcp://*:500")
        time.sleep(4)
        print "N disconnect"
        ns.test_peer_death()
        self.assertEqual(ns.get_services(), {'myremote': 'tcp://127.0.0.1:500', 'pizconaming': 'tcp://127.0.0.1:5777'})
        time.sleep(PeerWatcher.PING_INTERVAL*(PeerWatcher.LIFE_INTERVAL+0.5)*PeerWatcher.PEER_LIFES_AT_START)
        ns.test_peer_death_end()
        print "simulation of server object crash"
        s.stop()
        time.sleep(10)
        time.sleep(PeerWatcher.PING_INTERVAL*(PeerWatcher.LIFE_INTERVAL+5)) #ping standard time
        self.assertEqual(ns.get_services(), {'pizconaming': 'tcp://127.0.0.1:5777'})
        time.sleep(1)
        ns._proxy_stop_server()
        ns._proxy_stop_me()
        del ns
        time.sleep(2.5)
        
    def testNormalCase(self):
        print "##############NORMAL CASE SERVICE DEATH TEST###############"
        print "##"        
        LOGGER.setLevel(test_log_level)
        ns = Naming.start_naming_service(in_process=perform_test_in_process)
        self.assertNotEqual(ns, None)
        to = TestObject()
        s = Server(to,rep_endpoint="tcp://*:500")
        time.sleep(1)
        ns.register_local_service("myremote","tcp://*:500")
        addproxy = Proxy(ns.get_endpoint("myremote"),100)
        self.assertEqual(addproxy.times(50),50)
        time.sleep(5)
        self.assertEqual(ns.get_services(), {'myremote': 'tcp://127.0.0.1:500', 'pizconaming': 'tcp://127.0.0.1:5777'})
        time.sleep(1)
        s.stop()
        ns._proxy_stop_server()
        ns._proxy_stop_me()
        del ns
        time.sleep(2.5)
        

if __name__ == "__main__":
    freeze_support()
    LOGGER.setLevel(logging.DEBUG)
    ns = Naming.start_naming_service()
