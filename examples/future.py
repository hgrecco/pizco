# -*- coding: utf-8 -*-

import sys
import time

if sys.version_info < (3,0):
    input = raw_input

from pizco import Proxy

proxy = Proxy('tcp://127.0.0.1:8000')

while True:
    input('Press enter to run ...\n')
    fut = proxy.change_roof()
    print('I am doing something while changing the roof')
    print('The door is open?: {0}'.format(proxy.door_open))
    print('The lights are on?: {0}'.format(proxy.lights_on))
    print('I have finished doing this and now I will wait for the result')
    print(fut.result())

