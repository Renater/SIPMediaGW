SIPMediaGW
-----------------

A Docker based media gateway to be used on top of a web conferencing service, in order to provide SIP (audio+video) access.


<img src="docs/SIPMediaGW.png" width=50% height=50%>

Environment
--------

### <a name="devices">Virtual devices </a>###
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

Configuration
-----------

- **/browsing**

	This directory contains browsing scripts (python/selenium) to enter in a room of a specific web conferencing service.
	
- **/baresip**

	This directory contains  Baresip (https://github.com/baresip/baresip) related configuration files:

	- config_default

		Defaulf baresip configuration file used as a template configuration by the gateway.
		
	- tcpJsonCmd.py (+netstring.py)

		Remote controls baresip.
		
	- <a name="accounts">accounts</a>

		Where to configure SIP parameters (URI, register, TURN... ) of the gateways (one line per gateway).
		
		Example to be adapted and duplicated:
		
			<sip:user@domain;transport=tcp>;auth_pass=pass;answermode=auto;medianat=turn;stunserver=turn:turnserver.org:3478;stunuser=username;stunpass=password

  >	 **_NOTE:_** In the case of 4 gateways, this file must contain 4 different SIP accounts/lines
			
- **docker-compose.yml**

	The docker compose file.
	
- **entry_point.sh**

	Docker entry point which is actually the SIP media gateway implementation.

Build
-----------
	sudo docker-compose build

Usage
--------

Someone already connected to the webconference, e.g:

	google-chrome "https://rendez-vous.renater.fr/testRTCmediaGW"

 SIPMediaGW.sh is a helper script to automate gateway launching, is able to launch as many gateways (running in the same time) as there are account lines in the [account file](#accounts).

 Launch a gateway:

	SIPMediaGW.sh -r testRTCmediaGW-g my_gateway
  >	 **_NOTE:_** When running multiple gateways simultaneously, this script automatically check ressources availlability (assuming that they are dedicated to SIPMediaGW instances) but does not perform any [virtual devices provisionning](#devices).

Once the gateway is running, a SIP endpoint can join the room by calling the gateway via the SIP URIs (sip:user@domain) used by the gateway.

Stop a gateway:

	sudo docker-compose -p my_gateway stop
	
Troubleshoot
--------

Logs:

	tail -f logs/SIPWGXX_testRTCmediaGW_app.log
	tail -f logs/SIPWGXX_testRTCmediaGW_err.log
	
Restart Audio:

	sudo  pulseaudio -k && sudo alsa force-reload
	
Remove virtual devices:

	sudo modprobe -r snd_aloop
	sudo modprobe -r v4l2loopback
	
	
