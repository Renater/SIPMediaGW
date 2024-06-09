# SIPMediaGW

SIPMediaGW is a Docker-based media gateway to be used on top of a web conferencing service (Jitsi Meet, BigBlueButton, etc.), to provide SIP (audio+video) access.

<img src="docs/architecture.png" width=80% height=80%>

## Features

- Provides SIP access to web conferences
- Supports audio and video
- Easy to deploy with Docker
- Comprehensive SIP ecosystem
- Content sharing via BFCP (Binary Floor Control Protocol)
- Autoscaling logic for cloud deployement
- Streaming capabilities via RTMP (Real-Time Messaging Protocol) 

## Installation

The Room Connector can be easily deployed thanks to the "All-in-one" Vagrant file (requires Vagrant and VirtualBox).  
To do so, simply run:

```bash
VAGRANT_VAGRANTFILE=test/Vagrantfile vagrant up
```

Once the virtual machine is up, you can join a conference from your preferred SIP softphone:

* **Direct access** \
    sip:your_conference_name@192.168.75.13
* **IVR access** \
    sip:0@192.168.75.13

To use Baresip for testing:

```bash
./test/baresip/SIPCall.sh -u sip:test@192.168.75.1 -d 0@192.168.75.13
```
You can monitor the call by visiting [http://192.168.75.13](http://192.168.75.13) (with default [Homer credentials](https://github.com/sipcapture/homer/wiki/homer-seven-setup#homer-web-app)).


## Technical insights

- [Architecture](docs/architecture.md)
- [Call flow](docs/call_flow.md)
- [BFCP: Screen sharing from meeting room to web users](docs/BFCP.png)

## Open Source Projects Used

SIPMediaGW relies on several open-source projects:

- [Coturn](https://github.com/coturn/coturn)
- [Kamailio](https://github.com/kamailio/kamailio)
- [Homer](https://github.com/sipcapture/homer)
- [Baresip](https://github.com/baresip/baresip)
- [FFmpeg](https://github.com/FFmpeg/FFmpeg)
- [Pulseaudio](https://github.com/pulseaudio/pulseaudio)
- [ALSA](https://github.com/alsa-project/alsa-lib)
- [Video4Linux](https://linuxtv.org/)
- [Fluxbox](http://www.fluxbox.org/)
  <!---- [Chromium](https://github.com/chromium/chromium)--->

## FAQ

For frequently asked questions, please refer to our [FAQ](docs/FAQ.md).

## License

This project is licensed under the Apache 2.0 License. See the [LICENSE](LICENSE) file for details.
