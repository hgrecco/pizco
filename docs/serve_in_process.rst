Serve in process
----------------

You can directly start the server from the client application::

    from pizco import Server

    from myproject import Robot

    # The class (not the object!) is given as the first argument
    # and it returns a proxy to the served object.
    robot_proxy = Server.serve_in_process(Robot)

    robot_proxy.move_arm()

    print(robot_proxy.age)


A new process is started using the same python interpreter. `Pizco` will provide
this new process with the path of the `Robot` class but you need to be sure that
any other dependency is available.

If the `Robot` constructor takes some arguments you can give them like this::

    robot_proxy = Server.serve_in_process(Robot,
                                          args=('Robbie', ),
                                          kwargs={'age': 3})

Finally, you can ask `Pizco` to show the running server with a pop-up window::

    robot_proxy = Server.serve_in_process(Robot,
                                          args=('Robbie', ),
                                          kwargs={'age': 3},
                                          gui=True)

