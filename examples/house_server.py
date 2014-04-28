# -*- coding: utf-8 -*-

from pizco import Server

from common import House

s = Server(House(), 'tcp://127.0.0.1:8000')

s.serve_forever()

