class Jitsi extends UIHelper{
    constructor(domain, roomName, displayName, lang, prompts, token, audioOnly) {
        const wrapper = document.createElement('div');
        wrapper.id = 'wrapper';
        wrapper.style.cssText = `
            width: 100%;
            height: 100%;
            margin: 0;
            padding: 0;
            display: flex;
            pointer-events: none;
        `;
        document.body.appendChild(wrapper);
        super();
        this.wrapper = wrapper;
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
        this.passwordPrompt = JSON.parse(prompts)[lang]['password'];
        this.keyHandler = null;
    }

    onConferenceJoined = () => {
        this.overlay.style.display = "none";
        this.wrapper.style.display = 'block';
        this.joined = true;
        if (this.keyHandler && typeof this.keyHandler === "function") {
            document.removeEventListener('keydown', this.keyHandler, true);
        }
        if (this.jitsiApiClient) {
            this.jitsiApiClient.removeEventListener('videoConferenceJoined', this.onConferenceJoined);
        }
    };

    waitForPasswordRequired(timeoutMs = 5000) {
        return new Promise((resolve, reject) => {
            let timeoutId;

            const onPasswordRequired = () => {
                clearTimeout(timeoutId);
                if (this.jitsiApiClient) {
                    this.jitsiApiClient.removeEventListener('passwordRequired', onPasswordRequired);
                }
                resolve(true);
            };

            this.jitsiApiClient.addEventListener('passwordRequired', onPasswordRequired);

            timeoutId = setTimeout(() => {
                if (this.jitsiApiClient) {
                    this.jitsiApiClient.removeEventListener('passwordRequired', onPasswordRequired);
                }
                reject(new Error('Timeout waiting for passwordRequired'));
            }, timeoutMs);
        });
    }

    async join() {
        var externalAPI = document.createElement('script');
        externalAPI.onload = async () => {
            let subDomain = this.domain;
            this.jitsiApiClient = new JitsiMeetExternalAPI(subDomain, this.mainOptions);
            window.jitsiApiClient = this.jitsiApiClient;
            let passInput = false;

            this.jitsiApiClient.addEventListener('videoConferenceJoined', this.onConferenceJoined);

            try {
                passInput = await this.waitForPasswordRequired(10000);
            } catch (e) {
                console.warn("Password input not found or not clickable:", e);
                passInput = null;
            }
            if(passInput){
                this.overlay.style.display = "flex";
                this.setPromptMessage(this.passwordPrompt);
                this.passwordInput.value = "";
                this.passwordInput.focus();

                let passwordBuffer = "";

                this.keyHandler = (e) => {
                    const key = e.key;
                    if (key === '#') {
                        e.preventDefault();
                        if (passwordBuffer.length > 0 && this.jitsiApiClient) {
                            this.jitsiApiClient.executeCommand('password', passwordBuffer);
                        }
                        this.setPasswordDisplay("");
                        passwordBuffer = "";
                    } else if (key === '*' || key === 'Backspace') {
                        e.preventDefault();
                        passwordBuffer = passwordBuffer.slice(0, -1);
                        this.setPasswordDisplay(passwordBuffer);
                    } else if (/^[a-zA-Z0-9]$/.test(key)) {
                        e.preventDefault();
                        passwordBuffer += key;
                        this.setPasswordDisplay(passwordBuffer);
                    }
                };

                document.addEventListener('keydown', this.keyHandler, true);
                this.setPasswordDisplay(passwordBuffer);
                this.passwordInput.focus();
            }

            const onConferenceJoined = () => {
                debugger;
                this.overlay.style.display = "none";
                this.joined = true
                if (keyHandler === "function") {
                    document.removeEventListener('keydown', keyHandler, true);
                }
            };
            this.jitsiApiClient.addEventListener('videoConferenceJoined', onConferenceJoined);
            while (!this.joined) {
                await new Promise(resolve => setTimeout(resolve, 500));
                console.log("Waiting to join...");
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