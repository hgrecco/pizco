# -*- coding: utf-8 -*-

import time

from pizco import Server

from common import House

proxy = Server.serve_in_process(House, (), {}, 'tcp://127.0.0.1:8000')

time.sleep(1)

proxy.door_open = True
proxy.lights_on = True
time.sleep(.1)
proxy.paint('green')
proxy.lights_on = False
proxy.door_open = False

for step in range(3, 0, -1):
    time.sleep(1)
    print('Stopping in {}'.format(step))

proxy._proxy_stop_server()

print('Bye!')
