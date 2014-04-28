# -*- coding: utf-8 -*-
from __future__ import print_function

import sys
import time

if sys.version_info < (3,0):
    input = raw_input

from pizco import Proxy

proxy = Proxy('tcp://127.0.0.1:8000')

while True:
    try:
        proxy.paint(input('New color for the house: '))
    except ValueError as ex:
        print('Oops!')
        print(ex)
