# -*- coding: utf-8 -*-

import time
import argparse

from pizco import Server

from common import House

if __name__ == "__main__":
    parser = argparse.ArgumentParser('Start house server')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Print logging output')
    parser.add_argument('-g', '--gui', action='store_true',
                        help='Show graphical user interface')

    args = parser.parse_args()

    proxyA = Server.serve_in_process(House, (), {}, 'tcp://127.0.0.1:8000',
                                    verbose=args.verbose, gui=args.gui)
    proxyB = Server.serve_in_process(House, (), {}, 'tcp://127.0.0.1:8005',
                                     verbose=args.verbose, gui=args.gui)


    proxyA.door_open_changed.connect(proxyB.change_roof)

    time.sleep(1)

    proxyA.door_open = True
    time.sleep(10)
    proxyA.door_open = False

    for step in range(3, 0, -1):
        time.sleep(1)
        print('Stopping in {0}'.format(step))

    proxyA._proxy_stop_server()
    proxyB._proxy_stop_server()

    print('Bye!')
