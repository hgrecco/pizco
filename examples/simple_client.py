# -*- coding: utf-8 -*-

import sys
import time
import random

if sys.version_info < (3,0):
    input = raw_input

from pizco import Proxy

proxy = Proxy('tcp://127.0.0.1:8000')

colors = ('green', 'blue', 'white', 'yellow')

while True:
    input('Press enter to run ...\n')
    proxy.door_open = True
    proxy.lights_on = True
    time.sleep(.1)
    proxy.paint(random.choice(colors))
    proxy.lights_on = False
    proxy.door_open = False
