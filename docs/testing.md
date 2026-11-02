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

### Local environment on the host

To run Kamailio, TURN, the database and one gateway directly on your machine (no VM):

```
./test/environnement/local/start.sh     # BROWSING=jitsi by default
./test/environnement/local/stop.sh      # --purge also drops the Kamailio DB volume and gw_net
```

- `BROWSING` (default `jitsi`, empty for the IVR), `DOCKER_IMAGE` (default `sipmediagw:dev`, built if missing), `HOST_IP` (detected from the default route, never docker0; a loopback value is replaced by that detected address: `127.0.0.1` inside gw0 is the container itself, and TURN relays a host softphone's media only when `HOST_IP` is the address the softphone advertises) and `RTCSTATS_SERVER_URL` (turns rtcstats on) and `LOOP` (default `1`: gw0 is recreated after each call, as with `SIPMediaGW.sh --loop`; `0` to disable) can be set in the environment.
- The v4l2loopback devices are created from `/dev/video10`, so the script also works on a laptop whose webcams hold `/dev/video0`…; `sudo` is asked to load the kernel modules, and `stop.sh` unloads only the ones `start.sh` loaded.
- Then call `sip:<room>@HOST_IP` (or `sip:0@HOST_IP` for the IVR) from Linphone, as below, but with an identity whose domain is not `HOST_IP` (e.g. `sip:bob@softphone.local`): a softphone on the same host would otherwise use Kamailio's own address and get `407 Proxy Authentication Required`. The containers log to syslog: `journalctl -f | grep -E 'gw0|kamailio'`.

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

### Browser gateway (web client)

The gateway can also be the web client itself — no SIP softphone needed:

```
./SIPMediaGW.sh -a browser [-P "Salle de Conférence"] [-l]
```

The IVR (and later the meeting) open in the gateway's own Chromium, and you
drive it from the proxy's web UI: open the proxy (default
`http://<HOST_IP>:9000`, i.e. the `GW_PROXY` URL), pair with the code shown
on the gateway's IVR screen, pick the platform, enter the room name.

- **Raccrocher** ends the call at any IVR stage (it sends `/hangup` to the
  gateway's control port); with `-l` the gateway is recreated after each
  call, exactly as for baresip.
- With `-x N` the IVR displays on your desktop `:N`. Keystrokes (platform
  digit, `#`, room name) follow the **X focus**: if your own browser window
  has the focus, they land in it instead of the gateway's — keep the gateway
  window focused while entering the room name.
- Prerequisites: the proxy (`deploy/proxyAPI/docker-compose.yml`) and the
  host launcher (`python3 HTTPLauncher.py`, run from the repo root) must be
  running — the page's commands go proxy → launcher → gateway.
