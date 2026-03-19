## FAQ

### Can the All-in-One installation be used in a production environment, or is it necessary to install SIPMediaGW, Coturn, and Kamailio independently ?

The "All-in-one" [vagrant file](https://github.com/Renater/SIPMediaGW/blob/main/test/Vagrantfile) is mainly for testing purposes. \
In this case, the provisioning is managed by a simple [shell script](https://github.com/Renater/SIPMediaGW/blob/main/test/provision.sh) \
In production environemnt, we advice to deploy a specific VM for TURN (Coturn), a specific VM for Kamailio, and SIPMediaGW VMs in autoscaling. \
Coturn and Kamailio environment variables (especially IP adresses) need to be adapted regarding the target architecture.

### Does SIPMediaGW support SIP-TLS and SRTP ?

Yes, SIPMediaGW supports SIP-TLS (Transport Layer Security) and SRTP (Secure Real-time Transport Protocol).\
SIP-TLS is enabled by default at Kamailio side which serves as an 'edge proxy' for SIP. \
SIP-TLS can also be enabled at SIPMediaGW side for internal SIP communications (Kamailio<=>SIPMediaGW). \
SRTP can be activated through MEDIAENC variable.

### What does the stable version of SIPMediaGW on your GitHub correspond to ?

In theory, the main branch corresponds to a stable version.

### Do you have a simple way to test audio/video calls ?

For a simple test, you can use the Baresip [testing tool](https://github.com/Renater/SIPMediaGW/tree/main/test/baresip):
 	
	./test/baresip/SIPCall.sh -u sip:test@192.168.75.1 -d 0@192.168.75.13
 
### It works nicely with Baresip but I want to make a test with Linephone, can you help me ?

With Linphone, it is supposed to work, but it is sometimes a bit of a hassle to find the right configuration... \
This some screen shots of a working configuration (in french...) that you can use as starting point: sip account [[1]](https://github.com/Renater/SIPMediaGW/blob/main/docs/linphone/linephone.png)[[2](https://github.com/Renater/SIPMediaGW/blob/main/docs/linphone/sip_account1.png)][[3](https://github.com/Renater/SIPMediaGW/blob/main/docs/linphone/sip_account2.png)][[4](https://github.com/Renater/SIPMediaGW/blob/main/docs/linphone/sip_account3.png)], [audio codecs](https://github.com/Renater/SIPMediaGW/blob/main/docs/linphone/audio_codecs.png), [video codecs](https://github.com/Renater/SIPMediaGW/blob/main/docs/linphone/video_codecs.png), [network](https://github.com/Renater/SIPMediaGW/blob/main/docs/linphone/network.png)

 ### How to test SIPMediaGW with my own webconference service ?

By default, SIPMediaGW is configured to work with several webconference platforms.
When you make a call, the IVR will first prompt you to choose the webconference platform (for example: Jitsi Meet, BigBlueButton,Visio, or Livekit), and then ask for the meeting ID or name.

This list of available platforms is defined by the `WEBRTC_DOMAINS` variable in your `.env` file.
By default, the following platforms are configured:

```json
{
    "jitsi": { "name": "Jitsi Meet (rendez-vous.renater.fr)", "domain": "rendez-vous.renater.fr" },
    "bigbluebutton": { "name": "Big Blue Button (bigbluebutton.org)", "domain": "demo.bigbluebutton.org/rooms" },
    "visio": {"name": "Visio (visio.numerique.gouv.fr)", "domain": "visio.numerique.gouv.fr"},
    "livekit" : {"name": "Livekit (meet.livekit.io)", "domain": "meet.livekit.io/rooms"}
}
```

You can add or modify entries in this JSON to match your own webconference service or instance.
Simply update the `WEBRTC_DOMAINS` variable in your `.env` file with the appropriate service name and domain.
SIPMediaGW will then present these choices in the IVR menu, allowing you to select your platform before entering the meeting ID.

### SIPMediaGW being provided thourgh a dockerized envrironment, is it possible to deploy it in a Kubernetes cluster ?

At this stage, the advantage of Docker lies in the portability and deployment flexibility offered by the containerized approach. \
However, for performance reasons (latency), SIPMediaGW relies on virtual ALSA and Video4Linux devices from the host. \
This constraint will need to be addressed to have a fully containerized component and thus deployable in a Kubernetes cluster.
