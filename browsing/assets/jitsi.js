class Jitsi extends UIHelper{
    constructor(domain, roomName, displayName, lang, token, audioOnly) {
        document.body.innerHTML = '<div id="wrapper" style="width: 100%; height: 100%; margin: 0; padding: 0;"></div>';
        super();
        this.audioOnly = audioOnly === "true"
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
            parentNode: document.getElementById("wrapper"),
        };
        this.domain = domain;
        document.body.style.margin = '0';
        document.body.style.padding = '0';
        document.body.style.height = '100vh';
        document.body.style.width = '100vw';
        document.body.style.overflow = 'hidden';
        this.participantsPaneVisible = false;
        this.jitsiApiClient = null;
        this.joined = false;
    }

    getDocumentContent(){
        if(this.jitsiApiClient) {
            return this.jitsiApiClient.getIFrame().contentDocument;
        }
        super.getDocumentContent();
    }

    async join() {
        var externalAPI = document.createElement('script');
        externalAPI.onload = async () => {
            let subDomain = this.domain;
            this.jitsiApiClient = new JitsiMeetExternalAPI(subDomain, this.mainOptions);
            window.jitsiApiClient = this.jitsiApiClient;
            let passInput = null;
            let waitingHost = null;

            try {
                passInput = await this.waitForElement('#required-password-input',
                                                      { clickable: true },
                                                      2000);
            } catch (e) {
                console.warn("Password input not found or not clickable:", e);
                passInput = null;
            }

            if(passInput){
                this.overlay.style.display = "flex";
                try{
                    passInput.addEventListener('keydown', async (e) => {
                        const key = e.key;
                        if ( key === '#' ) {
                            e.preventDefault();
                            let okButton = await this.waitForElement('#modal-dialog-ok-button',
                                                      { clickable: true },
                                                      1000);
                            okButton.click();
                        }
                        if ( key === '*' ) {
                            e.preventDefault();
                            passInput.value = passInput.value.slice(0, -1);
                        }
                    }, {capture: true});
                } catch (err) {
                    console.error("Error during Menu setup:", err);
                    onError(err);
                }
            }

            // Wait until password input disappears or is disabled
            while (passInput) {
                passInput.focus();
                await new Promise(resolve => setTimeout(resolve, 500));
                passInput = this.jitsiApiClient.getIFrame().contentDocument.querySelector('#required-password-input');
                if (!passInput) break;
                console.log("Waiting for password input to disappear or be disabled");
            }
            // Hide overlay when done
            this.overlay.style.display = "none";

            // Look for CGU input and wait until it disappears
            try {
                waitingHost = await this.waitForElement("[data-focus-lock-disabled='false']",
                                                        { clickable: true },
                                                        2000);
            } catch (e) {
                console.warn("CGU notification not found:", e);
                passInput = null;
            }
            while (waitingHost) {
                await new Promise(resolve => setTimeout(resolve, 500));
                waitingHost = this.jitsiApiClient.getIFrame().contentDocument.querySelector("[data-focus-lock-disabled='false']");
                if (!waitingHost) break;
                console.log("Waiting for CGU input to disappear or be disabled");
            }

            this.blockerFocus()
            this.joined = true;
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