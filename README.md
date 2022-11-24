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

A more detailed description of this installation is available here: [SIPMediaGW in-depth](https://github.com/Renater/SIPMediaGW/blob/main/docs/sipmediagw-in-depth.md)



