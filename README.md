**SIPMediaGW** is a Docker based media gateway to be used on top of a web conferencing service (Jitsi Meet, BigBlueButton,...), in order to provide SIP (audio+video) access.


<img src="docs/architecture.png" width=80% height=80%>

The Room Connector can be easily deployed thanks to the "All-in-one" [vagrant file](https://github.com/Renater/SIPMediaGW/blob/main/Vagrantfile) (requires Vagrant and VirtualBox).\
To do so, simply run:

	vagrant up

> **Warning**\
> This is only for testing purposes
>
> **Note**\
> In this case, the provisioning is managed by a simple [shell script](https://github.com/Renater/SIPMediaGW/blob/main/test/provision.sh)

Once the virtual machin is up, you can join a conference from your preferred SIP softphone:

- **sip:0@192.168.75.13** (IVR access)
- **sip:your_conference_name@192.168.75.13** (Direct access)

SIPMediaGW in-depth
--------

### Docker network ### 

A user-defined bridge network to connect the gateways:

	docker network create  --subnet=192.168.92.0/29 gw_net

### SIP register and TURN server ###

To be accessible from any SIP endpoint, the gateway needs SIP registering facilities.
Kamailio is an open-source SIP server which can be easily installed.

To overcome NAT traversal issues, a TURN server acts as a media traffic relay. Coturn is an open-source STUN and TURN implementation.

Before starting the gateway, a local (docker based) testing environment (Kamailio and Coturn) may be simply started as follows:

	docker compose -f test/docker-compose.yml -p testing up -d --force-recreate

Usage
--------

SIPMediaGW.sh is a helper script to automate gateway launching, is able to launch as many gateways (running in the same time) as possible, in accordance with CPU_PER_GW environment variable value.
 > **Note**\
 > When running multiple gateways simultaneously, this script automatically check ressources availlability (assuming that all the CPU is dedicated to SIPMediaGW instances) but does not perform any [virtual video devices provisionning](#devices).

Launch a gateway:

	SIPMediaGW.sh

The gateway will automatically stop after the call is closed.


Troubleshoot
--------

Logs:

	tail -f /var/log/syslog | grep mediagw
	
Restart Audio:

	sudo  pulseaudio -k

Remove virtual devices:

	sudo modprobe -r v4l2loopback



