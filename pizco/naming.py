# -*- coding: utf-8 -*-
"""
    pyzco.naming
    ~~~~~~~~~~~~

    Implements a Naming service

    :copyright: 2013 by Hernan E. Grecco, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""

#
# UDP ping command
# Model 1
#

__all__ = ['Naming', ]

import socket
import time
import zmq
import os

from threading import RLock, Thread, Event
try:
    from . import Server, Signal, Proxy, LOGGER
except:
    pass
    from pizco import Server, Signal, Proxy, LOGGER

from functools import partial

from .compat import Queue, Empty, u

PZC_BEACON_PORT = os.environ.get('PZC_BEACON_PORT', 9999)
PZC_NAMING_PORT = os.environ.get('PZC_NAMING_PORT', 5777)




class PeerWatcher(Thread):
    PING_PORT_NUMBER = PZC_BEACON_PORT
    PING_MSG_SIZE = 1
    PING_INTERVAL = 1 # Once per second
    LIFE_INTERVAL = 3
    PEER_LIFES_AT_START = 5

    sig_peer_event = Signal(1)
    sig_peer_birth = Signal(1)
    sig_peer_death = Signal(1)

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
                exec_time = time.time() - start_time
            if self._exit_e.wait(self._periodicity):
                break
        self.sig_peer_event.disconnect()
        self._end_beacon()

    def process_queue(self):
        if self.is_alive():
            try:
                event = self._events.get(timeout=0.1)
            except Empty:
                pass
            else:
                event()

    def do_job(self):
        self._heartbeat += 1
        self._beacon_receive_job()
        if (self._heartbeat*self._periodicity%self.PING_INTERVAL) < self._periodicity:
            self._beacon_send_job()
        if (self._heartbeat*self._periodicity%self.LIFE_INTERVAL) < self._periodicity:
            self._life_job()

    def stop(self):
        LOGGER.debug("stopping peer watcher")
        self._job_e.clear()
        self._exit_e.set()
        self.join()  # self._periodicity*3
        LOGGER.debug("done stopping peers watcher")

    def _init_beacon(self):
        # Create UDP socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        # Ask operating system to let us do broadcasts from socket
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        # Bind UDP socket to local port so we can receive pings
        ntries = 3
        while ntries:
            try:
                sock.bind(('', self.PING_PORT_NUMBER))
            except socket.error as msg:
                sock.close()
                ntries -= 1
                continue
            else:
                break

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
            self._poller.unregister(self._sock)
            self._sock.close()
            self._sock = None
            del self._sock
            del self._poller

    def __del__(self):
        self.stop()

    def _beacon_receive_job(self):
        #dure au moins 1 seconde si des reponses dure moins de temps
        #LOGGER.debug("polling events for half periodicity")
        events = dict(self._poller.poll(self._periodicity * 100 / 2))
        # Someone answered our ping
        if self._sock.fileno() in events:
            msg, addrinfo = self._sock.recvfrom(self.PING_MSG_SIZE)
            LOGGER.debug("Found peer %s: %s", addrinfo, msg)
            self.sig_peer_event.emit(addrinfo[0])

    def _beacon_send_job(self):
        #LOGGER.debug(("Pinging peers"))
        self._sock.sendto(b'!', 0, ("255.255.255.255", self.PING_PORT_NUMBER))
        self.ping_at = time.time() + self.PING_INTERVAL
        #LOGGER.debug(time.time())

    def _life_job(self):
        death_list = []
        for k, v in self.peers_list.items():
            if v > 0:
                self.peers_list[k] = v-1
                if v >= self.PEER_LIFES_AT_START:
                    LOGGER.debug('promoted %s score %s', k, v)
                    self.sig_peer_birth.emit(u(k))
            else:
                LOGGER.debug('death of peer %s', k)
                death_list.append(k)
                self.sig_peer_death.emit(u(k))

        for k in death_list:
            self.peers_list.pop(k)


    def on_peer_event(self, addrinfo):
        evt = partial(self.delayed_peer_event,addrinfo=addrinfo)
        self._events.put(evt)
        
    def delayed_peer_event(self, addrinfo):
        LOGGER.debug(self.peers_list)
        if addrinfo in self.peers_list:
            if self.peers_list[addrinfo] < self.PEER_LIFES_AT_START:
                self.peers_list[addrinfo] += 1
        else:
            self.peers_list[addrinfo] = self.PEER_LIFES_AT_START

    @staticmethod
    def check_beacon_port(localonly=True):
        #returns true if the port is connectable free
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        # Ask operating system to let us do broadcasts from socket
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        # Bind UDP socket to local port so we can receive pings
        if localonly:
            address = '127.0.0.1'
        else:
            address = ''
        res = False
        try:
            sock.bind((address, PeerWatcher.PING_PORT_NUMBER))
        except socket.error as msg:
            sock.close()
            res = True
        else:
            sock.close()
        sock = None
        return res

        
        
import socket

class SocketChecker(object):
    def __init__(self,endpoint):
        ip,port = self._endpoint_to_connection(endpoint)
        self.ip = ip
        self.port = port
        if not self.check():
            raise Exception("Service port not opened tcp://{}:{}".format(ip,port))

    def check(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex((self.ip,self.port))
        if result == 0:
            sock.close()
            return True
        else:
            return False

    def _endpoint_to_connection(self,endpoint):
        edp = endpoint.split(":")
        ip = edp[1].replace("/","")
        port = int(edp[-1])
        return ip,port
    
class ProxyChecker(object):
    def __init__(self,endpoint):
        self.pxy = Proxy(endpoint,5000)
    def check(self):
        ret_code = self.pxy._proxy_ping(3000)
        if ret_code == "ping":
            return True
        else:
            return False
    def __del__(self):
        if hasattr(self,pxy):
            del self.pxy
        

class ServicesWatcher(Thread):

    CHECK_INTERVAL = 1
    sig_service_death = Signal(1)

    def __init__(self, method="socket"):
        assert(method in ["pizco","socket"])
        if method == "pizco":
            self.CheckClass = ProxyChecker
        elif method == "socket":
            self.CheckClass = SocketChecker
            
        super(ServicesWatcher,self).__init__(name="ServicesWatcher")
        self._exit_e = Event()
        self._job_e = Event()
        self._job_e.set()
        self._events = Queue(30)
        self._periodicity = 1
        self._heartbeat = 0
        #
        self._local_services = {}
        self._sl_RLock = RLock()
        LOGGER.debug("service watcher started")

    def __del__(self):
        self.stop()
        
    def run(self):
        LOGGER.info("starting run")
        exec_time = 0
        while not self._exit_e.isSet():
            if self._job_e.isSet():
                start_time = time.time()
                self.do_job()
                self.process_queue()
                exec_time = time.time()-start_time
            if self._exit_e.wait(self._periodicity):
                break
        self.end_watch()
        LOGGER.info("end main loop")

    def end_watch(self):
        del_list = []
        for k,v in self._local_services.items():
            del_list.append(v)
        for pxy in del_list:
            del pxy

    def do_job(self):
        self._heartbeat+=1
        self._local_services_ping_job()

    def process_queue(self):
        if self.is_alive():
            try:
                event = self._events.get(timeout=0.1)
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


    def register_local_proxy(self, servicename, endpoint):
        evtcbck = partial(self.delayed_register_local_proxy,servicename=servicename,endpoint=endpoint)
        self._events.put(evtcbck)
        
    def delayed_register_local_proxy(self, servicename, endpoint):
        LOGGER.debug("registering local proxy %s %s", servicename, endpoint)
        endpoint = endpoint.replace("*", "127.0.0.1")
        with self._sl_RLock:
            if servicename not in self._local_services:
                try:
                    self._local_services[servicename] = self.CheckClass(endpoint)
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    LOGGER.error("registering local proxy %s %s", servicename, endpoint)
            LOGGER.debug(self._local_services)

    def _local_services_ping_job(self):
        death_list = []
        with self._sl_RLock:
            for k,v in self._local_services.items():
                start_time = time.time()
                retcode = v.check()
                LOGGER.debug("check duration: %s", time.time() - start_time)
                LOGGER.debug("check server %s -> %s", k, retcode)
                if retcode:
                    pass
                else:
                    death_list.append(k)
                    
        for service in death_list:
            self.unregister_local_proxy(service)
            self.sig_service_death.emit(service)
            
    def unregister_local_proxy(self,service_name):
        LOGGER.info("proxy unregister")
        with self._sl_RLock:
            if service_name in self._local_services:
                pxy = self._local_services[service_name]
                self._local_services.pop(service_name)
                del pxy

global default_ignore_local_ip
default_ignore_local_ip = True

global default_service_watcher_method
default_service_watcher_method = "socket"

class Naming(Thread):
    NAMING_SERVICE_PORT = PZC_NAMING_PORT

    #sig_remote_services = Signal()
    sig_register_local_service = Signal(2)
    sig_unregister_local_service = Signal(1)

    sig_exportable_services = Signal(2)

    def __init__(self,local_only=False, ignore_local_ips=default_ignore_local_ip, check_mode = default_service_watcher_method):
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
        self._ignore_list = []
        
        if ignore_local_ips:
            self.ignore_ips(self._local_ip)

        self._servicesRLock = RLock()
        self._socketRLock = RLock()
        #self.sig_remote_services.connect(self._on_remote_services)

        #watch for peers in the neighboorhood responding to ping and having a naming service
        self._pwatcher = PeerWatcher(local_only)
        self._pwatcher.sig_peer_birth.connect(self.on_peer_birth)
        self._pwatcher.sig_peer_death.connect(self.on_peer_death)
        self._pwatcher.start()

        #watch for non responding services
        self._swatcher = ServicesWatcher(method=check_mode)
        self._swatcher.sig_service_death.connect(self.on_service_death)
        self.sig_register_local_service.connect(self._swatcher.register_local_proxy)

        self.sig_unregister_local_service.connect(self._swatcher.unregister_local_proxy)
        self.sig_unregister_local_service.connect(self.on_service_death)
        
        self._swatcher.start()

    @staticmethod
    def test__show_debug_log(self):
        import multiprocessing as mp
        import logging
        mp.log_to_stderr(logging.DEBUG)
        mp.get_logger().setLevel(logging.DEBUG)
        LOGGER.setLevel(logging.DEBUG)

    @staticmethod
    def set_ignore_local_ip(ignore):
        global default_ignore_local_ip
        default_ignore_local_ip = ignore

    @staticmethod
    def set_service_watcher_method(method):
        global default_service_watcher_method
        default_service_watcher_method = method
        
    def run(self):
        while not self._exit_e.isSet():
            if self._job_e.isSet():
                start_time = time.time()
                self.process_queue()
                exec_time = time.time()-start_time
            if self._exit_e.wait(self._periodicity):
                break

    def process_queue(self):
        if self.is_alive():
            try:
                event = self._events.get(timeout=0.1)
            except Empty:
                pass
            else:
                event()

    @staticmethod
    def get_local_ip():
        addrList = socket.getaddrinfo(socket.gethostname(), None)
        ipList=[]
        for item in addrList:
            if item[0] == 2:
                ipList.append(item[4][0])
        return ipList

    def stop(self):
        self.clear_peer_proxies()

        self.sig_register_local_service.disconnect()
        self.sig_unregister_local_service.disconnect()
        self.sig_unregister_local_service.disconnect()

        self._swatcher.stop()
        self._pwatcher.stop()

        LOGGER.debug("Stopping naming service")
        self._job_e.clear()
        self._exit_e.set()
        self.join()
        LOGGER.debug("Stopped naming service")

    def clear_peer_proxies(self):
        for pxy in self.peer_proxies.values():
            pxy.sig_exportable_services.disconnect()
            del pxy

    def __del__(self):
        self.stop()

    def ignore_ips(self,addrinfo_list):
        self._ignore_list += addrinfo_list
        
    @staticmethod
    def start_naming_service(in_process=True, check_mode="socket", local_only=False):
        if not PeerWatcher.check_beacon_port(local_only):
            #beacon port is free to use
            LOGGER.info("BEACON PORT AVAILLABLE")
            if local_only:
                address = "127.0.0.1"
            else:
                address = "*"

            rep_endpoint="tcp://"+address+":"+str(Naming.NAMING_SERVICE_PORT)
            kparams = {"local_only":local_only, "check_mode":check_mode}

            if in_process:
                LOGGER.info("starting server in a remote process")
                pxy = Server.serve_in_process(Naming, args=(),
                                              kwargs=kparams,
                                            rep_endpoint=rep_endpoint)
            else:
                LOGGER.info("starting server in a thread")
                pxy = Server.serve_in_thread(Naming, args=(),
                                             kwargs=kparams,
                                             rep_endpoint=rep_endpoint)
            pxy.start()
            pxy.register_local_service("pizconaming", rep_endpoint)
        else:
            #beacon port is not free
            LOGGER.info("BEACON PORT UNAVAILLABLE ACCESSING VIA PROXY")

            try:
                pxy = Proxy("tcp://127.0.0.1:" + str(Naming.NAMING_SERVICE_PORT))
                try:
                    LOGGER.info("CALLING GET SERVICES")
                    pxy.get_services()
                except:
                    LOGGER.error("Proxy is running neither")
                    pxy._proxy_stop_server()
                    del pxy
                    raise Exception("cannot call get services")
                    return None
            except Exception as e:
                if e.args[0] == "Timeout":
                    LOGGER.error("check hidden python processes")
                    raise Exception("timeout in reaching the naming service")
                    return None
                else:
                    import traceback
                    traceback.print_exc()
                    raise e
        return pxy

    def on_peer_death(self, addrinfo):
        LOGGER.debug("on peer death event")
        with self._servicesRLock:
            death_list = []
            for name, endpoint in self.remote_services.items():
                if addrinfo in endpoint:
                    death_list.append(name)
            for remote in death_list:
                self.remote_services.pop(remote)
        if addrinfo in self.peer_proxies:
            pxy = self.peer_proxies[addrinfo]
            pxy.sig_exportable_services.disconnect()
            self.peer_proxies.pop(addrinfo)
            del pxy

    def _make_remote_services_slot(self, addrinfo):
        def remote_services_slot(type, services):
            address = addrinfo
            self._on_remote_services(address, type, services)
        return remote_services_slot

    def on_peer_birth(self, addrinfo):
        if (not addrinfo in self.peer_proxies) and (not addrinfo in self._ignore_list):
            LOGGER.debug(addrinfo)
            try:
                rn_service = Proxy("tcp://{0}:{1}".format(addrinfo, self.NAMING_SERVICE_PORT),
                                   creation_timeout=2000)
            except:
                LOGGER.error("no naming service present at %s:%s", addrinfo, self.NAMING_SERVICE_PORT)
                #due to masquerading some ips must be ignored
                LOGGER.info("adding IP to ignore list %s", addrinfo)
                self.ignore_ips([addrinfo])

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
                    LOGGER.error("failure in connecting local proxy")

    def _on_remote_services(self, addrinfo, type, rservices):
        with self._servicesRLock:
            if type == "birth":
                for name,port in rservices.iteritems():
                    self.remote_services[name] = "tcp://{0}:{1}".format(addrinfo, port.split(":")[-1])
            elif type == "death":
                for name,port in rservices.iteritems():
                    if name in self.remote_services:
                        self.remote_services.pop(name)

    def get_endpoint(self,servicename):
        slist = self.get_services()
        if servicename in slist:
            return slist[servicename]
        else:
            return None

    def get_remote_services(self):
        with self._servicesRLock:
            return self.remote_services

    def get_services(self):
        #merge dict, keep only local services if names the same way
        with self._servicesRLock:
            z = self.remote_services.copy()
            z.update(self.local_services)
            return z

    def get_exportable_services(self):
        return self.exportable_local_services

    def register_local_service(self, service_name,endpoint):
        with self._servicesRLock:
            try:
                LOGGER.info("registering endpoint %s", endpoint)
                #ok only if the service is the local service not the proxy
                if endpoint.startswith("tcp://*"):
                    endpoint = endpoint.replace("*","127.0.0.1")
                    self.local_services[service_name] = endpoint
                    if service_name != "pizconaming":
                        self.exportable_local_services[service_name] = endpoint
                        self.sig_exportable_services.emit("birth", self.exportable_local_services.copy())
                elif not endpoint.startswith("tcp://127.0.0.1"):
                    #remote only managed service
                    self.exportable_local_services[service_name] = endpoint
                    if service_name != "pizconaming":
                        
                        self.sig_exportable_services.emit("birth", self.exportable_local_services.copy())
                else:
                    self.local_services[service_name] = endpoint
                if service_name != "pizconaming":
                    
                    self.sig_register_local_service.emit(service_name, endpoint)
            except:
                import traceback
                traceback.print_exc()
                LOGGER.error("cannot add service")

    def unregister_local_service(self,service_name):
        with self._servicesRLock:
            self.sig_unregister_local_service.emit(service_name)

    def on_service_death(self,service_name):
        if service_name in self.local_services:
            self.local_services.pop(service_name)
        if service_name in self.exportable_local_services:
            self.exportable_local_services.pop(service_name)
            self.sig_exportable_services.emit("death",{service_name:"now dead"})
        #remote local has the service name
        if service_name in self.remote_services:
            self.remote_services.pop(service_name)
        
    def test__peer_death(self):
        LOGGER.debug("disconnect")
        #self._pwatcher.sig_peer_event.disconnect()
        LOGGER.debug("disconnect done")

    def test__peer_death_end(self):
        self._pwatcher.sig_peer_event.connect(self._pwatcher.on_peer_event)

