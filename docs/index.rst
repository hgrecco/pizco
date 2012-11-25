
Pizco: Python remoting via ZMQ
==============================

.. image:: _static/pizco.png
   :alt: Pizco: remoting in Python with ZMQ
   :class: floatingflask

Pizco is Python module/package that allows python objects to communicate.
Objects can be exposed to other process in the same computer or over the network,
allowing clear separation of concerns, resources and permissions.

Pizco supports calling methods from remote objects and also
accessing their attributes, dictionary attributes and properties. Most importantly,
using a Qt-like (and Qt compatible!) signal and slot mechanism you can easily
register notifications.

As ZMQ is used as the transport layer, communication is fast and efficient,
and different protocols are supported. It has a complete test coverage.
It runs in Python 3.2+ and requires PyZMQ_. It is licensed under BSD.


Design principles
-----------------

- Reusable Agent class as communicating object for both Proxy and Server.

- ZMQ REP/REQ to handle sync access to objects.

- ZMQ PUB/SUB for notifications and async operations.

- PyQt-like signal and slots callbacks, compatible with PyQt.

- Transparent handling of methods that return concurrent.Futures.

- *Soon*: Asynchronous and batched operation on remote objects.

- Small codebase: small and easy to maintain codebase with a flat hierarchy.
  It is a single stand-alone module that can be installed as a package or added
  side by side to your project.

- *Soon*: Python 2 and 3: A single codebase that runs unchanged in Python 2.6+ and Python 3.0+.


Pizco in action
---------------

**example.py**::

    from PyQt4 import pyqtSignal as Signal

    class MultiplyBy(object):

        factor_changed = Signal()

        def __init__(self, factor):
            self._factor = factor

        def calculate(self, x):
            return x * self.factor

        @property
        def factor(self):
            return self._factor

        @factor.setter
        def factor(self, value):
            if self._factor == value:
                continue
            self.factor_changed.emit(value, self._factor)
            self._factor = value


**server.py**::

    from example import MultiplyBy

    from pizco import Server

    server = Server(MultiplyBy(2), 'tcp://127.0.0.1:8000')
    server.serve_forever()


**client.py**::

    import time

    from pizco import Proxy

    proxy = Proxy('tcp://127.0.0.1:8000')

    def on_factor_changed(new_value, old_value):
        print('The factor was changed from {} to {}'.format(old_value, new_value))
        print('{} * {} = {}'.format(proxy.factor, 8, proxy.calculate(8)))

    print('{} * {} = {}'.format(proxy.factor, 8, proxy.calculate(8)))

    for n in (3, 4, 5):
        proxy.factor = n
        time.sleep(.5)

Start the server in a terminal and run the client in another one::

    $ python client.py
    2 * 8 = 16
    The factor was changed from 2 to 3
    3 * 8 = 24
    The factor was changed from 3 to 4
    4 * 8 = 32
    The factor was changed from 4 to 5
    5 * 8 = 40

Contents
=========

.. toctree::
   :maxdepth: 2

   basic
   futures
   signals
   serve_in_process
   commandline
   internals
   api


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`



.. _PyZMQ: https://github.com/zeromq/pyzmq
.. _Pyro: http://packages.python.org/Pyro4/
