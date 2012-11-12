# -*- coding: utf-8 -*-

import time

from pizco import Proxy

def on_lights_on(value, old_value, others):
    print('The lights_on has been changed from {} to {}'.format(old_value, value))

def on_door_open(value, old_value, others):
    print('The front door has been changed from {} to {}'.format(old_value, value))

def on_color_change(value, old_value, others):
    print('The color has been changed from {} to {}'.format(old_value, value))

proxy = Proxy('tcp://127.0.0.1:8000')

connected = False
while True:
    input('Press enter to {} ...\n'.format('disconnect' if connected else 'connect'))
    if connected:
        proxy.lights_on_changed.disconnect(on_lights_on)
        proxy.door_open_changed.disconnect(on_door_open)
        proxy.color_changed.disconnect(on_color_change)
    else:
        proxy.lights_on_changed.connect(on_lights_on)
        proxy.door_open_changed.connect(on_door_open)
        proxy.color_changed.connect(on_color_change)
    connected = not connected
