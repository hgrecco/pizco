
Futures
-------

Starting from Python 3.2, :py:mod:`concurrent.futures` provides a high-level
interface for asynchronously executing callables (for older versions there is a
`Futures Backport`_)

The :py:class:`concurrent.futures.Future` class encapsulates the asynchronous
execution of a callable and `Pizco` has in-built support for it. Instead of
returning a `Future`, the Server will store it and notify the Proxy.
The proxy then returns a client-side `Future` connected to the original
server-side `Future`. The usage is just like normal `Futures` (there are just
that after all!)::

    from myproject import Robot

    from pizco import Proxy

    robot = Proxy('tcp://127.0.0.1:8000')

    # Move is a method from robot that returns a Future
    fut = robot.think('What do you get if you multiply six by nine?')

    # Do something here

    # fut is an instance of `Future`, therefore you can use the
    # methods and properties described in the Python docs
    answer = fut.result()

.. note:: Future.cancel() is not currently implemented.

.. _New Style Signals and Slots: http://www.riverbankcomputing.com/static/Docs/PyQt4/html/new_style_signals_slots.html
.. _PyQt: http://www.riverbankcomputing.com/software/pyqt/intro
.. _PySide: http://qt-project.org/wiki/PySide
.. _Futures Backport: http://pypi.python.org/pypi/futures
