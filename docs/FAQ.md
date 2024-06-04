## SIPMediaGW FAQ

### Is SIPMediaGW installed independently of Coturn and Kamailio in production, or is it an All-in-One installation?

The "All-in-one" [vagrant file](https://github.com/Renater/SIPMediaGW/blob/main/test/Vagrantfile) is mainly for testing purposes. \
In this case, the provisioning is managed by a simple [shell script](https://github.com/Renater/SIPMediaGW/blob/main/test/provision.sh) \
In production environemnt, we advice to deploy a specific VM for TURN (Coturn), a specific VM for Kamailio, and SIPMediaGW VMs in autoscaling. \
Coturn and Kamailio environment variables (especially IP adresses) need to be adapted regarding the target architecture.

### Does SIPMediaGW support SIP-TLS and SRTP?

Yes, SIPMediaGW supports SIP-TLS (Transport Layer Security) and SRTP (Secure Real-time Transport Protocol).\
Kamailio serves as the "edge proxy" for SIP, thus SIP-TLS is enabled by default in its configuration. \
SRTP can also be activated at the SIPMediaGW level (through MEDIAENC variable) for internal SIP communication: Kamailio<=>SIPMediaGW. \
For monitoring purposes it can be necessary to keep SIP-TLS disabled from SIPMediaGW side.

### What does the stable version of SIPMediaGW on your GitHub correspond to?

In theory, the main branch represents a stable version (releases are mainly for major milestones).

### Do you have a simple way to test audio/video calls?

For a simple test, you can use the Baresip [testing tool](https://github.com/Renater/SIPMediaGW/tree/main/test/baresip):
 	
	./test/baresip/SIPCall.sh -u sip:test@192.168.75.1 -d 0@192.168.75.13

 ### How to test SIPMediaGW with my own webconference service ?

By defaut SIPMediaGW is configured to work with the public instance of Jitsi Meet (meet.jit.si).\
Thanks to BROWSE_FILE and WEBRTC_DOMAIN variables, it is possible to make it work with others webconferencing services and instances.
