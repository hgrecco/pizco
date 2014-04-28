
import unittest

from pizco.util import bind, Signal, SignalError


class MockSocket(object):

    def bind(self, address):
        pass

    def bind_to_random_port(self, address):
        return 42


class Example(object):
    def __init__(self):
        self.signal = Signal(varargs=True)

    def emit(self, *args):
        self.signal.emit(*args)


class TestProtocol(unittest.TestCase):
    def test_bind_address(self):

        mock = MockSocket()
        self.assertEqual(bind(mock, 'tcp://127.0.0.1:5000'), 'tcp://127.0.0.1:5000')
        self.assertEqual(bind(mock, 'tcp://127.0.0.1:0'), 'tcp://127.0.0.1:42')
        self.assertEqual(bind(mock, ('127.0.0.1', 5000)), 'tcp://127.0.0.1:5000')
        self.assertEqual(bind(mock, ('127.0.0.1', 0)), 'tcp://127.0.0.1:42')
        self.assertEqual(bind(mock, 'inproc://bla'), 'inproc://bla')


class TestSignal(unittest.TestCase):
    def test_signal(self):
        def noargs():
            pass

        def arg1(a):
            pass

        def arg2(a, b):
            pass

        def arg2def1(a, b, c=1):
            pass

        def arg2kwargs(a, b, **kwargs):
            pass

        def args(*args):
            pass

        def kwargs(**kwargs):
            pass

        def argskwargs(*args, **kwargs):
            pass

        s = Signal()  # no args or kwargs
        for f in (noargs, args, argskwargs, kwargs):
            s.connect(f)
        for f in (arg1, arg2, arg2def1, arg2kwargs):
            with self.assertRaises(SignalError):
                s.connect(f)
        s.emit()
        with self.assertRaises(SignalError):
            s.emit(1)
        with self.assertRaises(SignalError):
            s.emit(a=1)

        s = Signal(nargs=1)
        for f in (arg1, args, argskwargs):
            s.connect(f)
        for f in (noargs, arg2, arg2def1, arg2kwargs, kwargs):
            with self.assertRaises(SignalError):
                s.connect(f)
        s.emit(1)
        with self.assertRaises(SignalError):
            s.emit()
        with self.assertRaises(SignalError):
            s.emit(1, 2)
        with self.assertRaises(SignalError):
            s.emit(a=1)

        s = Signal(nargs=2)
        for f in (arg2, arg2def1, arg2kwargs, args, argskwargs):
            s.connect(f)
        for f in (noargs, arg1, kwargs):
            with self.assertRaises(SignalError):
                s.connect(f)
        s.emit(1, 2)
        with self.assertRaises(SignalError):
            s.emit()
        with self.assertRaises(SignalError):
            s.emit(1)
        with self.assertRaises(SignalError):
            s.emit(1, 2, 3)
        with self.assertRaises(SignalError):
            s.emit(a=1)

        s = Signal(nargs=3)
        for f in (arg2def1, args, argskwargs):
            s.connect(f)
        for f in (noargs, arg1, arg2, arg2kwargs, kwargs):
            with self.assertRaises(SignalError):
                s.connect(f)
        s.emit(1, 2, 3)
        with self.assertRaises(SignalError):
            s.emit()
        with self.assertRaises(SignalError):
            s.emit(1, 2)
        with self.assertRaises(SignalError):
            s.emit(1, 2, 3, 4)
        with self.assertRaises(SignalError):
            s.emit(a=1)

        s = Signal(nargs=4)
        for f in (args, argskwargs):
            s.connect(f)
        for f in (noargs, arg1, arg2, arg2def1, arg2kwargs, kwargs):
            with self.assertRaises(SignalError):
                s.connect(f)
        s.emit(1, 2, 3, 4)
        with self.assertRaises(SignalError):
            s.emit()
        with self.assertRaises(SignalError):
            s.emit(1, 2, 3)
        with self.assertRaises(SignalError):
            s.emit(1, 2, 3, 4, 5)
        with self.assertRaises(SignalError):
            s.emit(a=1)

        s = Signal(varargs=True)
        for f in (args, argskwargs):
            s.connect(f)
        for f in (noargs, arg1, arg2, arg2def1, arg2kwargs, kwargs):
            with self.assertRaises(SignalError):
                s.connect(f)
        s.emit()
        s.emit(1)
        s.emit(1, 2)
        with self.assertRaises(SignalError):
            s.emit(a=1)

        s = Signal(varkwargs=True)
        for f in (argskwargs, kwargs):
            s.connect(f)
        for f in (noargs, arg1, arg2, arg2def1, arg2kwargs, args):
            with self.assertRaises(SignalError):
                s.connect(f)
        s.emit()
        s.emit(a=1)
        with self.assertRaises(SignalError):
            s.emit(1)
        with self.assertRaises(SignalError):
            s.emit(1, 2)

        s = Signal(varargs=True, varkwargs=True)
        for f in (argskwargs, ):
            s.connect(f)
        for f in (noargs, arg1, arg2, arg2def1, arg2kwargs,
                  args, kwargs):
            with self.assertRaises(SignalError):
                s.connect(f)
        s.emit()
        s.emit(1)
        s.emit(1, a=1)
        s.emit(a=1)

        s = Signal(nargs=2, kwargs=['c'])
        for f in (arg2def1, arg2kwargs, argskwargs):
            s.connect(f)
        for f in (noargs, arg1, arg2, args, kwargs):
            with self.assertRaises(SignalError):
                s.connect(f)
        s.emit(1, 2)
        s.emit(1, 2, c=3)
        with self.assertRaises(SignalError):
            s.emit(1)
        with self.assertRaises(SignalError):
            s.emit(1, 2, d=4)
        with self.assertRaises(SignalError):
            s.emit(c=3)

    def test_socket_args_through_proxy(self):
        # open proxy serving Example
        # have it emit a 1 arg signal
        # watch if it becomes 3 args
        pass

if __name__ == '__main__':
    unittest.main()
