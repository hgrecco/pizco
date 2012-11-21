
Installing
----------

To install `Pizco` you need to to install PyZMQ_ following the instructions here_.
If you are having trouble at this step, a few Python distributions like EPD_ and
Anaconda_ have PyZMQ_ preinstalled.

Then install, `Pizco` using pip_ or easy_install_::

    $ easy_install pizco

or::

    $ pip install pizco


Basic usage
-----------

Consider the::

    from myproject import Robot

    robot = Robot()

    print(robot.name)
    robot.move_arm()
    robot.age = 28


`Pizco` provides two classes t:

- Server: wraps an object and exposes its attributes via a ZMQ socket.
- Proxy: connects to a server, redirects attribute request to it,
  and collect the response.

Creating a Server is quite simple, just instantiate a Server using the object
as the first parameter::

    # This is your stuff
    from myproject import Robot

    from pizco import Server

    server = Server(Robot())

If no endpoint is given, the server will bind to a random tcp port.

You can specify the endpoint with the second argument::

    server = Server(Robot(), 'tcp://127.0.0.1:8000')

Any valid ZMQ endpoints_ is valid:

- **inproc**: local in-process (inter-thread) communication transport

  *example*: inproc://robbie-the-robot

- **ipc**: local inter-process communication transport

  *example*: ipc://robbie-the-robot

- **tcp**: unicast transport using TCP

  *example*: tcp://127.0.0.1:8000

In the client side, you need to create a proxy::

    from pizco import Proxy

    robot = Proxy('tcp://127.0.0.1:8000')

and now you can use the proxy as if it was the actual object::

    print(robot.name)
    robot.move_arm()
    robot.age = 28

Notice that the only needed change was to the initialization code.


Remote exceptions
-----------------

Exception in the served object are caught remotely and re-raised by the proxy
and therefore the following code::

    try:
        robot.age = input()
    except ValueError as ex:
        print('That is not a valid age for the robot')

will work the same way if the robot is the actual object or just a Proxy to it.

.. note:: The remote traceback is not propagated the proxy in the current
   version of `Pizco`.




.. _here: http://www.zeromq.org/bindings:python
.. _EPD: http://www.enthought.com/products/epd_free.php
.. _Anaconda: https://store.continuum.io/cshop/anaconda
.. _PyZMQ: https://github.com/zeromq/pyzmq
.. _pip: http://pypi.python.org/pypi/pip
.. _easy_install: http://pypi.python.org/pypi/setuptools
.. _intro: http://nichol.as/zeromq-an-introduction
.. _endpoints: http://api.zeromq.org/2-1:zmq-bind
