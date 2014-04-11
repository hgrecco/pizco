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
    addproxy = Proxy(ns.get_endpoint("myremote"),100)
    addproxy._proxy_stop_server()