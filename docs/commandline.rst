
Command line tool
=================

You can start a server from the command line calling `pizco.py`. For example::

    $ python pizco.py tcp://127.0.0.1:8000
    Server started at tcp://127.0.0.1:8000
    Press CTRL+c to stop ...

will start a server bound to localhost, port 8000. If you want to bind to a
particular pub endpoint, you can specify it with an extra parameter.

When the server is created in this way, no object is served. To instantiate
and serve an object, create a proxy, connect to it and call the instantiate method::

    from myproject import Robot

    proxy = Proxy('tcp://127.0.0.1:8000')
    proxy._proxy_agent.instantiate(Robot,
                                   args=('Robbie', ),
                                   kwargs={'age': 3})


Additional arguments can be used to configure the server:

**-g**: open a small window to display the server status.
      If the window is closed, the server is stopped.

**-v**: print debug information to the console.

**-p** *path*: add *path* to sys.path


This is script is called under the hood by `serve_in_process` to initiated
a server in detached processes.
