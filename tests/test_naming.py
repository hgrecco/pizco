import unittest
from pizco.naming import TestNamingService
from pizco.naming import configure_test
import logging
configure_test(logging.INFO,False)

if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestNamingService)
    unittest.TextTestRunner(verbosity=100).run(suite)
    #unittest.main("pizco.naming","TestNamingService.test_wildcards")

    #unittest.main("pizco.naming","TestNamingService.testServiceWatcher")
    #unittest.main("pizco.naming","TestNamingService.testPeerWatcher")
    #unittest.main("pizco.naming","TestNamingService.testNormalCase")
    #unittest.main("pizco.naming","TestNamingService.testNormalCaseServiceDeath")
    #unittest.main("pizco.naming","TestNamingService.testARemoteCase")
    #unittest.main("pizco.naming","TestNamingService.testARemoteCaseMulti")

