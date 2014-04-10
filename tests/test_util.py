
import unittest

from pizco.util import bind, Signal


class MockSocket(object):

    def bind(self, address):
        pass

    def bind_to_random_port(self, address):
        return 42


class Example(object):
    def __init__(self):
        self.signal = Signal()

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
    def test_socket_args(self):
        s = Signal()

        def two(a, b):
            self.assertEqual(a, 1)
            self.assertEqual(b, 2)

        s.connect(two)
        s.emit(1, 2, 3)
        s.emit(1, 2)
        with self.assertRaises(TypeError):
            s.emit(1)
        s.disconnect()

        def vargs(*args):
            for a in args:
                self.assertEqual(a, len(args))

        s.connect(vargs)
        s.emit(1)
        s.emit(2, 2)
        s.emit(3, 3, 3)

    def test_socket_args_through_proxy(self):
        # open proxy serving Example
        # have it emit a 1 arg signal
        # watch if it becomes 3 args
        pass

if __name__ == '__main__':
    unittest.main()
