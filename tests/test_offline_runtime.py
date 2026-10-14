"""외부 호출 차단·호출 인자 미저장·예외 후 복구를 확인한다."""
import socket
import unittest
from src.offline_runtime import deny_network, NetworkAccessBlocked


class OfflineRuntimeTests(unittest.TestCase):
    def test_pure_local_work_has_no_network_attempts(self):
        with deny_network() as attempts:
            self.assertEqual(sum([1, 2, 3]), 6)
        self.assertEqual(attempts, [])

    def test_dns_is_blocked_without_resolving_address(self):
        with deny_network() as attempts:
            with self.assertRaises(NetworkAccessBlocked):
                socket.getaddrinfo('example.invalid', 443)
        self.assertEqual(attempts, ['getaddrinfo'])

    def test_connect_and_datagram_are_blocked(self):
        with socket.socket() as connection, deny_network() as attempts:
            with self.assertRaises(NetworkAccessBlocked):
                connection.connect(('203.0.113.1', 443))
            with self.assertRaises(NetworkAccessBlocked):
                connection.connect_ex(('203.0.113.1', 443))
            with self.assertRaises(NetworkAccessBlocked):
                connection.sendto(b'no-transmission', ('203.0.113.1', 443))
        self.assertEqual(attempts, ['connect', 'connect_ex', 'sendto'])

    def test_originals_restored_after_exception(self):
        original = socket.socket.connect
        with self.assertRaises(ValueError):
            with deny_network():
                raise ValueError('test exception')
        self.assertIs(socket.socket.connect, original)

    def test_caught_call_is_still_recorded(self):
        with deny_network() as attempts:
            try:
                socket.create_connection(('203.0.113.1', 443))
            except NetworkAccessBlocked:
                pass
        self.assertEqual(attempts, ['create_connection'])


if __name__ == '__main__':
    unittest.main()
