SIPMediaGW
-----------------

A Docker based media gateway to be used on top of a web conferencing service, in order to provide SIP (audio+video) access.


<img src="docs/SIPMediaGW.png" width=50% height=50%>

Environment 
--------

### Virtual devices ###
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

		Where to specify the  SIP parameters of the gateway (URI, register, TURN... ).
		
		Example to be adapted:
		
			Displayname<sip:user@domain;transport=tcp>;auth_pass=pass;answermode=auto;medianat=turn;stunserver=turn:turnserver.org:3478;stunuser=username;stunpass=password
			
- **docker-compose.yml**

	The docker compose file, provided here with a single gateway configuration.
	
	Video device id and GW_ID should be incremented when adding others gateways.
  
  >	 **_NOTE:_** A specific account file must be provided for each gateway.
	
- **entry_point.sh**

	Docker entry point which is actually the SIP media gateway implementation.


Usage
--------
Someone already connected to the webconference, e.g: 
 
	google-chrome "https://rendez-vous.renater.fr/testRTCmediaGW"

Launch a gateway:

	sudo docker-compose up
	
Once the gateway is running, a SIP endpoint can join the room by calling the gateway, through the SIP URI (sip:user@domain) configurated in the [account file](#accounts).
	
Troubleshoot
--------

Baresip logs:

	tail -f logs/SIPWG0_baresip_xxxxxxx.log
	
Restart Audio:

	sudo  pulseaudio -k && sudo alsa force-reload
	
Remove virtual devices:

	sudo modprobe -r snd_aloop
	sudo modprobe -r v4l2loopback
	
	
