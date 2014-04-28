
import unittest

from pizco.protocol import Protocol

class TestProtocol(unittest.TestCase):

    def test_protocol(self):
        prot = Protocol()
        self.assertRaises(ValueError, prot.parse, [])

        msg = prot.format('friend', 'bla', 'here goes the content')
        sender, topic, content, msgid = prot.parse(msg)
        self.assertEqual(sender, 'friend')
        self.assertEqual(topic, 'bla')
        self.assertEqual(content, 'here goes the content')

        real_id = msg[1]
        msg[1] = 'newid'.encode('utf-8')
        self.assertRaises(ValueError, prot.parse, msg, check_msgid='wrong id')
        self.assertRaises(ValueError, prot.parse, msg, check_sender='another')
        msg[-1] = 'fake signature'.encode('utf-8')
        msg[1] = real_id
        self.assertEqual(sender, 'friend')
        self.assertEqual(topic, 'bla')
        self.assertEqual(content, 'here goes the content')

    def test_protocol_key(self):
        prot = Protocol(hmac_key='have a key')

        msg = prot.format('friend', 'bla', 'here goes the content')
        sender, topic, content, msgid = prot.parse(msg)
        self.assertEqual(sender, 'friend')
        self.assertEqual(topic, 'bla')
        self.assertEqual(content, 'here goes the content')

        real_id = msg[1]
        msg[1] = 'newid'.encode('utf-8')
        self.assertRaises(ValueError, prot.parse, msg, check_msgid='wrong id')
        self.assertRaises(ValueError, prot.parse, msg, check_sender='another')
        msg[-1] = 'fake signature'.encode('utf-8')
        msg[1] = real_id
        self.assertRaises(ValueError, prot.parse, msg)

if __name__ == '__main__':
    unittest.main()
