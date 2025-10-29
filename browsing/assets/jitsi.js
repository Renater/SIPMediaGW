class Jitsi {
    constructor(domain, roomName, displayName, lang, token, audioOnly) {
        document.body.innerHTML = '<div id="jitsi-container" style="width: 100%; height: 100%; margin: 0; padding: 0;"></div>';
        this.audioOnly = audioOnly === "true"
        debugger;
        this.mainOptions = {
            roomName: roomName,
            userInfo: {
                displayName: displayName
            },
            jwt: token,
            interfaceConfigOverwrite: {
                CLOSE_PAGE_GUEST_HINT: true,
                SHOW_CHROME_EXTENSION_BANNER: false
            },
            configOverwrite: {
                disableDeepLinking: true,
                noSSL: false,
                callStatsID: '',
                defaultLanguage: lang,
                toolbarButtons: ['security'],
                startWithAudioMuted: false,
                startWithVideoMuted: this.audioOnly,
                startAudioOnly: this.audioOnly,
                enableNoisyMicDetection: false,
                prejoinPageEnabled: false,
                videoQuality: {
                    codecPreferenceOrder: ['VP8', 'H264']
                },
                prejoinConfig: {
                    enabled: false
                },
                autoKnockLobby: true,
                p2p: { enabled: false },
                desktopSharingChromeDisabled: false,
                disableShortcuts: true,
                buttonsWithNotifyClick: [
                    'hangup'
                ],
                toolbarConfig: {
                    alwaysVisible: true
                },
                testing: { no_customUI: true },
                screenShareSettings: {
                    desktopSystemAudio: 'exclude',
                    desktopDisplaySurface: 'monitor'
                },
                disableSelfView: false
            },
            parentNode: document.getElementById("jitsi-container"),
        };
        this.domain = domain;
        document.body.style.margin = '0';
        document.body.style.padding = '0';
        document.body.style.height = '100vh';
        document.body.style.width = '100vw';
        document.body.style.overflow = 'hidden';
        this.participantsPaneVisible = false;
        this.jitsiApiClient = null;
    }
    join() {
        var externalAPI = document.createElement('script');

        externalAPI.onload = () => {
            let subDomain = this.domain;
            this.jitsiApiClient = new JitsiMeetExternalAPI(subDomain, this.mainOptions);
            window.jitsiApiClient = this.jitsiApiClient;
        };
        externalAPI.src = "https://" + this.domain + "/external_api.js"
        document.body.appendChild(externalAPI);
    }
    getParticipantNum() {
        if (!this.jitsiApiClient) {
            console.warn("Jitsi API client not initialized");
            return 0;
        }
        try {
            return this.jitsiApiClient.getNumberOfParticipants();
        } catch (e) {
            console.error("Error while requesting the number of participants :", e);
            return 0;
        }
    }
    interact(key) {
        if (key == "1")
            this.jitsiApiClient.executeCommand('toggleAudio');
        if (key == "2")
            this.jitsiApiClient.executeCommand('toggleVideo');
        if (key == "3")
            this.jitsiApiClient.executeCommand('toggleChat');
        if (key == "4")
            this.jitsiApiClient.executeCommand('toggleRaiseHand');
        if (key == "5") {
            this.participantsPaneVisible = !this.participantsPaneVisible;
            this.jitsiApiClient.executeCommand('toggleParticipantsPane', this.participantsPaneVisible);
        }
        if (key == "6")
            this.jitsiApiClient.executeCommand('toggleTileView');
        if (key == "7")
            this.jitsiApiClient.executeCommand('toggleLobby');
        if (key == "8")
            this.jitsiApiClient.executeCommand('muteEveryone');
        if (key == "s")
            this.jitsiApiClient.executeCommand('toggleShareScreen');
    }
    leave() {
        try {
            if (this.jitsiApiClient && document.querySelector('#jitsiConferenceFrame0')) {
                this.jitsiApiClient.dispose();
            } else {
                return;
            }
            const start = Date.now();
            const interval = setInterval(() => {
                if (!document.querySelector('iframe')) {
                    clearInterval(interval);
                } else if (Date.now() - start > 5000) {
                    clearInterval(interval);
                }
            }, 1000);
        } catch (e) {
            console.error(e);
            console.log('Iframe error: ' + e);
        }
    }
}

window.Jitsi = Jitsi;
window.Browsing = Jitsi;