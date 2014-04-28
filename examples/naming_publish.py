import time

from pizco import Proxy, LOGGER, Server
from pizco.naming import Naming
import time
import logging

class TestObject(object):
    def __init__(self):
        self._times = 0
    def times(self,multiply):
        self._times *= multiply

if __name__ ==  "__main__":
    LOGGER.setLevel(logging.DEBUG)
    ns = Naming.start_naming_service()
    to = TestObject()
    s = Server(to,rep_endpoint="tcp://*:500")
    ns.register_local_service("myremote","tcp://*:500")
    addproxy = Proxy(ns.get_endpoint("myremote"),100)
    while True:
        time.sleep(10)