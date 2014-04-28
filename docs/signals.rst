
Signals and Slots (registering callbacks)
-----------------------------------------

If a served object exposes a Qt signal (or Qt-like signals), you can connect
a slot to it in the proxy. If you are not familiar with the Qt jargon, this
is equivalent to bind (*connect*) a callback (*slot*) to an event (*signal*).

The syntax in the client side is exactly as it is done in PyQt_/PySide_
`New Style Signals and Slots`_::

    def print_notification(new_position):
        print('The arm has been moved to {}'.format(new_position))

    proxy = Proxy('tcp://127.0.0.1:8000')

    proxy.arm_moved.connect(print_notification)

Under the hood, the proxy is subscribing to an event in the server
using a ZMQ SUB socket. When the `arm_moved` signal is emitted server-side,
the server will **asynchronously** notify the proxy using a PUB socket.
The proxy will call `print_notification` when it receives message. So you
have client side notification of server side events.

It is important to note that if you are using PyQt/PySide signals in your
code, no modification is needed to use `Pizco`. But not only PyQt/PySide
signals work. An attribute is considered `Signal` if it exposes at least
three methods: `connect`, `disconnect` and `emit`.

Just like PyQt, multiple slots can be connected to the same signal::

    proxy.arm_moved.connect(print_notification)
    proxy.arm_moved.connect(mail_notification)

and they will be called in the order that they were added.

To disconnect from a signal::

    proxy.arm_moved.disconnect(mail_notification)

Additionally, you can connect in another proxy::

    proxy2 = Proxy('tcp://127.0.0.1:8000')

    proxy2.arm_moved.connect(mail_notification)

Proxy connections to signals are independent and therefore disconnecting
in one proxy will not have an effect on another.


.. _New Style Signals and Slots: http://www.riverbankcomputing.com/static/Docs/PyQt4/html/new_style_signals_slots.html
.. _PyQt: http://www.riverbankcomputing.com/software/pyqt/intro
.. _PySide: http://qt-project.org/wiki/PySide
