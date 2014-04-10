import time

from pizco import Proxy, LOGGER
from pizco.naming import Naming
import logging

if __name__ ==  "__main__":
    LOGGER.setLevel(logging.DEBUG)
    ns = Naming.start_naming_service()
    ns.get_services()
    time.sleep(4)
    pxy = ns.get_endpoint("myremote")
    print pxy
    r = Proxy(ns.get_endpoint("myremote"))
    while True:
        time.sleep(1)
        print r.times(3.121)
        print ns.get_services()
        ns._proxy_ping()
    ns._proxy_stop_me()