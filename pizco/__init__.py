# -*- coding: utf-8 -*-
"""
    pizco
    ~~~~~

    A small remoting framework with notification and async commands using ZeroMQ.

    :copyright: 2013 by Hernan E. Grecco, see AUTHORS for more details.
    :license: BSD, see LICENSE for more details.
"""

import os
import sys
import logging

logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

DEFAULT_LAUNCHER = os.environ.get('PZC_DEFAULT_LAUNCHER', None)

if not DEFAULT_LAUNCHER:
    sw = sys.platform.startswith
    if sw('linux'):
        DEFAULT_LAUNCHER = r"""xterm -e "{0[python]} {0[pizco]} {0[rep_endpoint]} {0[pub_endpoint]} """ \
                           r"""-p {0[cwd]} {0[verbose]} """
    elif sw('win32'):
        DEFAULT_LAUNCHER = r"""cmd.exe /k "{0[python]} {0[pizco]} {0[rep_endpoint]} {0[pub_endpoint]} """\
                           r"""-p {0[cwd]} {0[verbose]} """
    elif sw('darwin'):
        DEFAULT_LAUNCHER = r"""osascript -e 'tell application "Terminal"' """\
                           r""" -e 'do script "\"{0[python]}\" \"{0[pizco]}\" {0[rep_endpoint]} {0[pub_endpoint]} """
        r"""-p \"{0[cwd]}\" {0[verbose]}"' """\
                           r""" -e 'end tell' """
        #DEFAULT_LAUNCHER = r"""screen -d -m {0[python]} {0[pizco]} {0[rep_endpoint]} {0[pub_endpoint]} -p  {0[cwd]}"""

from .clientserver import Proxy, Server, Signal, Agent

def main():
    import argparse
    parser = argparse.ArgumentParser('Starts an server')
    parser.add_argument('-g', '--gui', action='store_true',
                        help='Open a small window to display the server status.')
    parser.add_argument('-v', '--verbose', action='store_true',
                        help='Print debug information to the console.')
    parser.add_argument('-p', '--path', type=str,
                        help='Append this path to sys.path')
    parser.add_argument('rep_endpoint',
                        help='REP endpoint of the Server')
    parser.add_argument('pub_endpoint',
                        help='PUB endpoint of the Server')

    args = parser.parse_args()

    if args.path:
        sys.path.append(args.path)

    if args.verbose:
        logger.addHandler(logging.StreamHandler())
        logger.setLevel(logging.DEBUG)

    s = Server(None, args.rep_endpoint, args.pub_endpoint)
    print('Server started at {}'.format(s.rep_endpoint))
    if args.gui:
        if sys.version_info < (3, 0):
            from TKinter import Tk, Label
        else:
            from tkinter import Tk, Label

        import time

        while s.served_object is None:
            time.sleep(.1)

        name = s.served_object.__class__.__name__

        root = Tk()
        root.title('Pizco Server: {}'.format(name))
        Label(root, text='{}'.format(name)).pack(padx=5)
        Label(root, text='REP: {}'.format(s.rep_endpoint)).pack(padx=5)
        Label(root, text='PUB: {}'.format(s.pub_endpoint)).pack(padx=5)
        root.resizable(width=False, height=False)
        root.mainloop()
    else:
        print('Press CTRL+c to stop ...')
        s.serve_forever()

    print('Server stopped')
