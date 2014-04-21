import unittest
from pizco.naming import TestNamingService

if __name__ == "__main__":
    suite = unittest.TestLoader().loadTestsFromTestCase(TestNamingService)
    unittest.TextTestRunner(verbosity=2).run(suite)
    #unittest.main("pizco.naming","TestNamingService.testServiceWatcher")
    #unittest.main("pizco.naming","TestNamingService.testProcessWatcher")
    #unittest.main("pizco.naming","TestNamingService.testNormalCase")
    #unittest.main("pizco.naming","TestNamingService.testNormalCaseServiceDeath")
    #unittest.main("pizco.naming","TestNamingService.testARemoteCase")
    #unittest.main("pizco.naming","TestNamingService.testARemoteCaseMulti")

