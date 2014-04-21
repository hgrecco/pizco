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
import subprocess
import warnings

import zmq

if (zmq.zmq_version_info()[0] < 3):
    warnings.warn(
        "ZMQ version {} < 3, notifications will not work".format(
            zmq.zmq_version()))

LOGGER = logging.getLogger(__name__)
LOGGER.addHandler(logging.NullHandler())


def main(args=None):
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

    args = parser.parse_args(args)

    if args.path:
        sys.path.append(args.path)

    if args.verbose:
        LOGGER.addHandler(logging.StreamHandler())
        LOGGER.setLevel(logging.DEBUG)

    from pizco import Server
    s = Server(None, args.rep_endpoint, args.pub_endpoint)
    print('Server started at {}'.format(s.rep_endpoint))
    if args.gui:
        if sys.version_info < (3, 0):
            from Tkinter import Tk, Label
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


def launch(cwd, rep_endpoint, pub_endpoint, verbose=True, gui=False):
    if cwd == '':
        cwd = '.'
    launcher = os.environ.get('PZC_DEFAULT_LAUNCHER', None)

    if not launcher:
        sw = sys.platform.startswith
        if sw('linux'):
            launcher = r"""xterm -e "{0[python]} {0[pizco]} {0[rep_endpoint]} {0[pub_endpoint]} """ \
                       r"""-p {0[cwd]} {0[verbose]} {0[gui]}" """
        elif sw('win32'):
            launcher = r"""cmd.exe /k "{0[python]} {0[pizco]} {0[rep_endpoint]} {0[pub_endpoint]} """\
                       r"""-p {0[cwd]} {0[verbose]} {0[gui]} """
        elif sw('darwin'):
            launcher = r"""osascript -e 'tell application "Terminal"' """\
                       r""" -e 'do script "\"{0[python]}\" \"{0[pizco]}\" {0[rep_endpoint]} {0[pub_endpoint]} """ \
                       r"""-p \"{0[cwd]}\" {0[verbose]} {0[gui]}"' """ \
                       r""" -e 'end tell' """
        else:
            raise RuntimeError('Platform not support: {}'.format(sys.platform))

    o = dict(python=sys.executable, pizco=__file__,
             rep_endpoint=rep_endpoint, pub_endpoint=pub_endpoint,
             cwd=cwd, verbose='')

    o['verbose'] = '-v' if verbose else ''
    o['gui'] = '-g' if gui else ''

    cmd = launcher.format(o)

    subprocess.Popen(cmd, cwd=cwd, shell=True)


if __name__ == '__main__':
    main()
else:
    from .clientserver import Proxy, Server, Signal, Agent
