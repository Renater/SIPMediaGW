### Testing the SIPMediaGW
Once the services are up and running, you can join a conference from your preferred SIP softphone by calling the following SIP addresses : 

  - Direct access to your conference (for example https://jitsi.domain.com/your_conference_name)
    ```
    sip:your_conference_name@KAMAILIO_IP_ADDRESS
    ``` 
  - Home page that allows IVR access
    ```
    sip:0@KAMAILIO_IP_ADDRESS
    ```

### Testing with Baresip

We provide a bash script that runs a SIP call via Baresip.
To launch the script, simply replace `KAMAILIO_IP_ADDRESS` with the corresponding IP address and run the following command:
```
./test/baresip/SIPCall.sh -u sip:test@YOUR_IP -d 0@KAMAILIO_IP_ADDRESS
```

### Testing with Linphone
It is also possible to perform tests from a SIP client such as Linphone. 
1. Download and install [Linphone](https://www.linphone.org/)
2. Add an account (in Preferences) [[1](./linphone/linephone.png)] [[2](./linphone/sip_account1.png)] [[3](./linphone/sip_account2.png)] [[4](./linphone/sip_account3.png)]
   1.  SIP Address: `sip:username@YOUR_IP`
   2.  SIP Server address : `<sip:YOUR_IP;transport=tls>`
   3.  **Disable** the following options : `Register`, `Publish presence information`, `Enable AVPF`, `Enable ICE`, `Bundle mode`
3.  In [the audio section](./linphone/audio_codecs.png), it is recommended to disable all codecs except `PCMU`, `PCMA` and `G722`
4.  In [the video section](./linphone/video_codecs.png), it is recommended to disable all codecs except `H265` and `H264`
5.  In [the network section](./linphone/network.png), select `SIP INFO` and disable `IPV6`. If you are in a local network, disable ICE/STUN option too.
6.  Open your jitsi conference in the browser (for example : `https://jitsi.domain.com/myConference`)
7.  Launch a new SIP call from the call menu in Linphone
   1.  `sip:myConference@KAMAILIO_IP_ADDRESS` for direct access to the conference `myConference`
   2.  `sip:0@KAMAILIO_IP_ADDRESS` for DTMF access (ConfMapper should be configured)
