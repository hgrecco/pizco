PIZCO NAMING SYSTEM
===================

Objectives
-----------

Providing a distributed naming system, similar to bonjour/avahi but for pizco objects only.


Rough Architecture
-------------------

The naming server consist in 3 components:

- A beacon that does UDP broadcast/receive on wildcard address on port PZC_BEACON_PORT(default:9999)

- A service watchdog system that ping registered services/server on localhost:service_port at 1second interval

- A Naming service (which is a pizco server) that takes care of 

    - the new hosts (via the beacon and hosts that disconnects)
        + by connecting their Naming Service (pizco server) and their registered services.
        
    - the new services (via a client interface (for registering) and via the service watchdog which looks for
      services that disconnects)
      
    - No polling is required due to the nature of signal and slots.
     
Known issues
--------------

- No helpers function to register *:0 services only by name / add hostname.service automatic naming. 
/ add hostname.service-x for service allready existing.

- Knowaday beacon and watchdog are threaded that could be moved to *:0 pizco objects for further performance.

- udp_broadcast_relay must be use for complex network, require rebuilding on some routers.

- Another issue is the question of who starts it's naming server on the system (on windows) because of the lack of fork, the naming system will be destroyed when the first app (having start the server) will close. The naming service proxy will then hang on clients if launched. And naming service of the host will disappear, leaving services unnamed.

	Two options :
	- Start the naming system independently of pizco using programs.

	- Another option is to start the naming service in another executable (not as a child process of python) that remains loaded (which will be addressed by pizco utils)

	- [not simple algo, long way ahead] Another option is to distribute the execution of the naming system between main processes, maybe a signal sent to other processes using the naming service can be used to respawn the server. or the proxy of the naming system, should be ping/polling the naming server. And restart as a new service if exiting, with the local service list.
			   + When the naming sytem is started as a Proxy Only
						 + create a pizco object that can receive signal from the naming server's process death and relaunch the server)
						 + create a pizco object that polls something (process, beacon port and relaunch the server).

			   + keep a list of numbered proxies with rank (second started will be responsible for restarting the proxy if it finds the beacon missing / or receive the signal from the main thread (with the local proxies list)). lower the rank of all other proxies.

			   + if the second proxy disconnects/or starts the server, it registers the restart to the third etc.

			   + restart the proxies if the previous proxy stops. will be complicated.