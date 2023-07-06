Overview
--------

**SIPMediaGW** is a Docker based media gateway to be used on top of a web conferencing service (Jitsi Meet, BigBlueButton,...), in order to provide SIP (audio+video) access.


<img src="docs/architecture.png" width=80% height=80%>

The Room Connector can be easily deployed thanks to the "All-in-one" [vagrant file](https://github.com/Renater/SIPMediaGW/blob/main/Vagrantfile) (requires Vagrant and VirtualBox).\
To do so, simply run:

	vagrant up

> **Note**\
> In this case, the provisioning is managed by a simple [shell script](https://github.com/Renater/SIPMediaGW/blob/main/test/provision.sh)

Once the virtual machin is up, you can join a conference from your preferred SIP softphone:

- **sip:your_conference_name@192.168.75.13** (Direct access)
- **sip:0@192.168.75.13** (IVR access => Jitsi Meet only)

Depending on [BROWSE_FILE](https://github.com/Renater/SIPMediaGW/blob/114ee4be29e0460132a0c018b8bbd94c72728522/.env#L12) and [WEBRTC_DOMAIN](https://github.com/Renater/SIPMediaGW/blob/114ee4be29e0460132a0c018b8bbd94c72728522/.env#L13) variables, the corresponding webconference is:
- jitsi (default): https://meet.jit.si/your_conference_name \
or
- bigbluebutton: https://demo.bigbluebutton.org/rooms/your_conference_name/join

Technical insights
--------
- Architecture: [SIPMediaGW in-depth](https://github.com/Renater/SIPMediaGW/blob/main/docs/sipmediagw-in-depth.md)
- Call flow: [SIPMediaGW call flow](https://github.com/Renater/SIPMediaGW/blob/main/docs/call_flow.md)
- BFCP: [Screen sharing from meeting room to web users](https://github.com/Renater/SIPMediaGW/blob/main/docs/BFCP.png)


