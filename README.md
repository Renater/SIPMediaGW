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

Once the virtual machin is up, you can join a conference (replace "your_conference_name" with yours) from your preferred SIP softphone:

- **sip:your_conference_name@192.168.75.13** (Direct access)
- **sip:0@192.168.75.13** (IVR access => available only with Jitsi Meet)

Depending on [BROWSE_FILE](https://github.com/Renater/SIPMediaGW/blob/main/.env#L9) and [WEBRTC_DOMAIN](https://github.com/Renater/SIPMediaGW/blob/main/.env#L10) variables, the corresponding webconference is one of these:
- jitsi: https://meet.jit.si/your_conference_name
- bigbluebutton: https://demo.bigbluebutton.org/rooms/your_conference_name/join

A more detailed description of this project is available here: [SIPMediaGW in-depth](https://github.com/Renater/SIPMediaGW/blob/main/docs/sipmediagw-in-depth.md)



