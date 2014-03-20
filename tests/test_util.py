
import unittest

from pizco.util import bind


class MockSocket(object):

    def bind(self, address):
        pass

    def bind_to_random_port(self, address):
        return 42


class TestProtocol(unittest.TestCase):
    def test_bind_address(self):

        mock = MockSocket()
        self.assertEqual(bind(mock, 'tcp://127.0.0.1:5000'), 'tcp://127.0.0.1:5000')
        self.assertEqual(bind(mock, 'tcp://127.0.0.1:0'), 'tcp://127.0.0.1:42')
        self.assertEqual(bind(mock, ('127.0.0.1', 5000)), 'tcp://127.0.0.1:5000')
        self.assertEqual(bind(mock, ('127.0.0.1', 0)), 'tcp://127.0.0.1:42')
        self.assertEqual(bind(mock, 'inproc://bla'), 'inproc://bla')

if __name__ == '__main__':
    unittest.main()
