SIPMediaGW in-depth
--------
<img src="SIPMediaGW.png" width=50% height=50%>

Environment
--------

### <a name="devices">Virtual devices </a>
Example for 4 gateways, co-hosted on GW_server machine:

- **Audio**

		sudo apt-get install -y linux-modules-extra-$(uname -r)
		echo "options snd-aloop enable=1,1,1,1,1,1,1,1 index=0,1,2,3,4,5,6,7" | sudo tee  /etc/modprobe.d/alsa-loopback.conf
		echo "snd-aloop" | sudo tee -a /etc/modules
		sudo modprobe snd-aloop

- **Video**

		sudo apt-get install -y v4l2loopback-dkms
		echo "options v4l2loopback devices=4 exclusive_caps=1,1,1,1" | sudo tee  /etc/modprobe.d/v4l2loopback.conf
		echo "v4l2loopback" | sudo tee -a /etc/modules
		sudo modprobe v4l2loopback

### Docker network ### 

A user-defined bridge network to connect the gateways:

	docker network create  --subnet=192.168.92.0/29 gw_net

### SIP register and TURN server ###

To be accessible from any SIP endpoint, the gateway needs SIP registering facilities.
Kamailio is an open-source SIP server which can be easily installed.

To overcome NAT traversal issues, a TURN server acts as a media traffic relay. Coturn is an open-source STUN and TURN implementation.

Before starting the gateway, a local (docker based) testing environment (Kamailio and Coturn) may be simply started as follows:

	docker compose -f deploy/docker-compose.yml -p testing up -d --force-recreate

Usage
--------

SIPMediaGW.sh is a helper script to automate gateway launching, is able to launch as many gateways (running in the same time) as possible, in accordance with [CPU_PER_GW](https://github.com/Renater/SIPMediaGW/blob/main/.env#L6) environment variable value.
 > **Note**\
 > When running multiple gateways simultaneously, this script automatically check ressources availlability (assuming that all the CPU is dedicated to SIPMediaGW instances) but does not perform any virtual video devices provisionning.

Launch a gateway:

	SIPMediaGW.sh

The gateway will automatically stop after the call is closed.


Troubleshoot
--------

Logs:

	tail -f /var/log/syslog | grep mediagw
	
Inspect Kamailio database:

	docker run -it --network=host --entrypoint mysql mysql -h 127.0.0.1 -u root -pdbrootpw kamailio -e "SELECT username, locked, to_stop FROM location"
