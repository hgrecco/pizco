# -*- coding: utf-8 -*-

from pizco import Server

from common import House

s = Server.serve_in_process(
    House, args=(), kwargs={}, rep_endpoint='tcp://127.0.0.1:8000',
    gui=True, verbose=True)
