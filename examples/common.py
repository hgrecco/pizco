# -*- coding: utf-8 -*-

import time
import logging

from concurrent import futures

from pizco import Signal



logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
logger.addHandler(ch)

COLORS = ('green', 'blue', 'white', 'yellow')

class House(object):

    def __init__(self):
        logger.info('Welcome to your new house')
        self._door_open = False
        self._lights_on = False

        self.door_open_changed = Signal()
        self.lights_on_changed = Signal()

        self.color_changed = Signal()

        self._pool = futures.ThreadPoolExecutor(max_workers=1)

    @property
    def door_open(self):
        logger.info('Getting door_open')
        return self._door_open

    @door_open.setter
    def door_open(self, value):
        if value not in (True, False):
            raise ValueError("'{}' is not a valid value for door_open".format(value))
        logger.info('Setting door_open to {}'.format(value))
        if self._door_open == value:
            logger.info('No need to change door_open')
            return

        self.door_open_changed.emit(value, self._door_open)
        self._door_open = value

    @property
    def lights_on(self):
        return self._lights_on

    @lights_on.setter
    def lights_on(self, value):
        if value not in (True, False):
            raise ValueError("'{}' is not a valid value for lights_on".format(value))
        logger.info('Setting lights_on to {}'.format(value))
        if self._lights_on == value:
            logger.info('No need to change lights_on')
            return
        self.lights_on_changed.emit(value, self._lights_on)
        self._lights_on = value

    def paint(self, color):
        if color not in COLORS:
            raise ValueError("'{}' is not a valid color ({})".format(color, COLORS))
        logger.info('Painting: {}'.format(color))
        time.sleep(.5)
        self.color_changed.emit(color)
        logger.info('Painted: {}'.format(color))

    def _changing_roof(self):
        time.sleep(1)
        return 'You have a new roof'

    def change_roof(self):
        return self._pool.submit(self._changing_roof)


