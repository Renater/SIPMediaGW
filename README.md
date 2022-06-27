SIPMediaGW
-----------------

A Docker based media gateway to be used on top of a web conferencing service (Jitsi Meet, BigBlueButton,...), in order to provide SIP (audio+video) access.


<img src="docs/SIPMediaGW.png" width=50% height=50%>

Environment
--------

### <a name="devices">Virtual devices </a>
Example for 4 gateways, co-hosted on GW_server machine:

- **Audio**

		sudo apt-get install linux-image-extra-virtual
		echo "options snd-aloop enable=1,1,1,1,1,1,1,1 index=0,1,2,3,4,5,6,7" | sudo tee  /etc/modprobe.d/alsa-loopback.conf
		echo "snd-aloop" | sudo tee -a /etc/modules
		sudo modprobe snd-aloop

- **Video**

		sudo apt-get install v4l2loopback-utils
		echo "options v4l2loopback devices=4 exclusive_caps=1,1,1,1" | sudo tee  /etc/modprobe.d/v4l2loopback.conf
		echo "v4l2loopback" | sudo tee -a /etc/modules
		sudo modprobe v4l2loopback

### SIP register ###

To be accessible from any SIP endpoint, the gateway needs SIP registering facilities.
Kamailio is an open-source SIP server which can be easily installed (https://kamailio.org/docs/tutorials/devel/kamailio-install-guide-deb/).

Briefly, it can be installed as follows:

	sudo apt-get install kamailio kamailio-mysql-modules kamailio-tls-modules

The main configuration files with TLS support are provided here: [kamailio.cfg](docs/kamailio.cfg) , [tls.cfg](docs/tls.cfg)


 >	 **_NOTE:_** Configuration lines related to domain name need to be adapted with your owns. Alternatively a public IPv4 address might be used.
 
### TURN server ###

To overcome NAT traversal issues, a TURN server acts as a media traffic relay. 
Coturn is an open-source STUN and TURN implementation:

	sudo apt-get install coturn

A minimalist configuration is provided here: [turnserver.conf](docs/turnserver.conf)

Implementation
-----------

- **entry_point.sh**

	Docker entry point (~ submodules launcher).

- **/src**

	Core functions implementation.

Configuration
-----------

- **/browsing**

	This directory contains browsing scripts (python/selenium) to enter in a room of a specific web conferencing service.

- **/baresip**

	This directory contains  Baresip (https://github.com/baresip/baresip) related configuration files:

	- config_default

		Defaulf baresip configuration file used as a template configuration by the gateway.
		
	- netstring.py

		TCP control interface tools.

- **<a name="config">sipmediagw.cfg</a>**

	Configuration file where to set: the SIP server address, a secret used by the gateways for SIP registration, TURN server address and credentials.
	
- **/ivr**

	This directory contains some files (audio prompt, background image, fonts..) related to Interactive Voice Response (IVR).

- **docker-compose.yml**

	The docker compose file.

- **Docker network**

		docker network create  --subnet=192.168.92.0/29 gw_net

Build
-----------
	docker image build -t sipmediagw .

Usage
--------

Someone already connected to the webconference, e.g:

	google-chrome "https://rendez-vous.renater.fr/testmediagw"

 SIPMediaGW.sh is a helper script to automate gateway launching, is able to launch as many gateways (running in the same time) as possible, in accordance with *cpuCorePerGw* parameter value fixed in [sipmedia.cfg](https://github.com/Renater/SIPMediaGW/blob/main/sipmediagw.cfg).

 Launch a gateway:

	SIPMediaGW.sh -r testmediagw -f "sip:endpoint@domain.com"
  >	 **_NOTE:_** When running multiple gateways simultaneously, this script automatically check ressources availlability (assuming that all the CPU is dedicated to SIPMediaGW instances) but does not perform any [virtual devices provisionning](#devices).

Once the gateway is running, a SIP endpoint can join the room by calling the gateway via the SIP URIs used by the gateway.
  >    **_NOTE:_**  -r and -f arguments are optional:
 If "-r" (room) argument is not passed, the SIP endpoint will connect first to an IVR. By default a 10 digits number is expected as a room name by the audio prompt.
 If "-f" (SIP URI of the caller) argument is passed, the gateway will reject calls from any other endpoints.
 
Alternatively, HTTPLauncher.py provides a way to launch a gateway by sending an http request. 

Start the http server:

	python HTTPLauncher.py

Launch a gateway:

	curl "http://192.168.92.1:8080/sipmediagw?room=testmediagw"

Once the gateway runs, a complete (docker based) testing environment may be simply started as follows:

	cd test && docker build -t kamailio .
	./kamailioCreateDb.sh
	docker compose -p testing up -d --force-recreate
	
In this way, the webconference can be joined by pushing a call directly to **sip:testmediagw@192.168.92.1**

The gateway will automatically stop after the call is closed.
	
Troubleshoot
--------

Logs:

	tail -f /var/log/syslog | grep mediagw
	
Restart Audio:

	sudo  pulseaudio -k && sudo alsa force-reload
	
Remove virtual devices:

	sudo modprobe -r snd_aloop
	sudo modprobe -r v4l2loopback

	
	
