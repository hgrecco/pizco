import unittest
from pizco.naming import TestNamingService

if __name__ == "__main__":
    print "ERRORS when not in start_in_process thread is stopped restarted, check ioloop reinit, when sending dictionnaries"
    unittest.main()
    #unittest.main("pizco.naming","TestNamingService.testServiceWatcher")
    #unittest.main("pizco.naming","TestNamingService.testProcessWatcher")
    #unittest.main("pizco.naming","TestNamingService.testNormalCase")
    unittest.main("pizco.naming","TestNamingService.testNormalCaseServiceDeath")


