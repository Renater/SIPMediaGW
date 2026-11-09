class Teams extends UIHelper {
    constructor(domain, roomName, displayName, lang, prompts, token, audioOnly) {
        super();
        this.domain = domain;
        this.roomName = roomName;
        this.displayName = displayName;
        this.lang = lang;
        this.token = token;
        this.joinded = false;
        this.passwordPrompt = JSON.parse(prompts)[lang]['password'];
    }

    async join() {
        try {
            console.log('[INFO] Waiting for display name input...');
            let nameInput;
            try {
                nameInput = await this.waitForElement("[data-tid='prejoin-display-name-input']", { visible: true }, 60000);
            } catch (e) {
                console.error('[✗] Name field not found:', e);
                return;
            }
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            nativeInputValueSetter.call(nameInput, this.displayName);
            nameInput.dispatchEvent(new Event('input', { bubbles: true }));

            console.log('[INFO] Submitting join form...');
            let joinButton;
            try {
                joinButton = await this.waitForElement("[data-tid='prejoin-join-button']", { clickable: true }, 60000);
            } catch (e) {
                console.error('[✗] Join button not found:', e);
                return;
            }
            joinButton.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
            console.log('[✓] Join form submitted');
            this.blockerFocus()
            this.joined = true;
        } catch (error) {
            console.error('[✗] Prejoin process failed:', error);
        }
    }

    // --- State read back for the room macro and interact -----------------------
    // Teams exposes no aria-pressed / data-state on its call buttons. What was found
    // stable (data-tid, set by Teams developers) is used first; the microphone and
    // camera are only readable through their label, which follows the browser
    // language: unknown wording gives null ("does not say"), never a guess.
    // Observed on teams.microsoft.com (light meeting, anonymous guest), Nov. 2026.

    isVisible(selector) {
        const el = document.querySelector(selector);
        return !!(el && el.getClientRects().length);
    }

    buttonLabel(id) {
        const el = document.getElementById(id);
        return el ? (el.getAttribute('aria-label') || '') : null;
    }

    mediaState() {
        const mic = this.buttonLabel('mic-button');
        const cam = this.buttonLabel('video-button');
        if (mic === null && cam === null) {
            return null;                     // not in the call (lobby, left)
        }
        // The label names the action available: "Réactiver le micro" = muted.
        const micOn = !mic ? null
            : /r[ée]activer|unmute/i.test(mic) ? false
            : /couper|mute/i.test(mic) ? true : null;
        const camOn = !cam ? null
            : /d[ée]sactiver|turn camera off|stop video/i.test(cam) ? true
            : /activer|turn camera on|start video/i.test(cam) ? false : null;
        return {
            microphone: micOn,
            camera: camOn,
            canPublishMicrophone: null,
            canPublishCamera: null
        };
    }

    panelState() {
        return {
            chat: this.isVisible('[data-tid="chat-pane-compose-message-footer"]'),
            participants: this.isVisible('[data-tid="calling-roster-attendees"]'),
            info: null,
            handRaised: this.ownHandRaised()
        };
    }

    // The raised-hand outline is drawn on the video tile of whoever raised it, so
    // only the outline found in the room's own tile counts. Without a tile carrying
    // the display name, the answer is null rather than someone else's hand.
    ownHandRaised() {
        const outlines = [...document.querySelectorAll('[data-tid="raise-hand-stream-outline"]')];
        if (outlines.length === 0) {
            return false;
        }
        const name = (this.displayName || '').trim().toLowerCase();
        if (!name) {
            return null;
        }
        for (const o of outlines) {
            for (let p = o.parentElement, depth = 0; p && depth < 8; p = p.parentElement, depth++) {
                const label = ((p.getAttribute('aria-label') || '') + ' ' + (p.getAttribute('data-tid') || '')).toLowerCase();
                if (label.includes(name)) {
                    return true;
                }
            }
        }
        return null;
    }

    uiState() {
        return {
            media: this.mediaState(),
            panels: this.panelState(),
            screenShare: null
        };
    }

    microphone(param) {
        const state = this.mediaState();
        if (!state || state.microphone === null) {
            return false;
        }
        if ((param === 'on') !== state.microphone) {
            this.clickById('mic-button');
        }
        return true;
    }

    camera(param) {
        const state = this.mediaState();
        if (!state || state.camera === null) {
            return false;
        }
        if ((param === 'on') !== state.camera) {
            this.clickById('video-button');
        }
        return true;
    }

    // Teams re-renders its call bar (the chat button goes missing while a side
    // panel closes): a missing button is logged instead of throwing.
    clickById(id) {
        const el = document.getElementById(id);
        if (!el) {
            console.error('[✗] Button not found: ' + id);
            return false;
        }
        el.click();
        return true;
    }

    async interact(key) {
        if (key == "1")
            this.clickById('mic-button');
        if (key == "2")
            this.clickById('video-button');
        if (key == "3" || key == "c")
            this.clickById('chat-button');
        if (key == "4")
            this.clickById('raisehands-button');
        if (key == "5")
            this.clickById('roster-button');
        if (key == "s" || key == "q") {
            document.querySelector('button#share-button, button#screenshare-button')?.click();
            try {
                const shareTabBtn = await this.waitForElement('[data-tid="share-screen-window-or-tab"]', { clickable: true }, 10000);
                shareTabBtn.click();
            } catch (e) {
                // No share picker (e.g. stopping an ongoing share)
                console.log('[INFO] Share picker not shown:', e.message);
            }
        }
    }

    async sendChat(message) {
        const ed = document.querySelector('div[data-tid="ckeditor"]').ckeditorInstance;
        ed.setData('<p>' + message + '</p>');
        document.querySelector('button[data-tid="newMessageCommands-send"]')?.click();
        const waitRetry = () => {
            const retry = document.querySelector('button[data-tid="message-failed-retry"]');
            if (retry) {
                retry.click();
                return;
            }
            setTimeout(waitRetry, 200);
        };
        setTimeout(waitRetry, 500);
    }

    async leave() {
        console.log('[INFO] Leave the meeting room');
        try {
            document.querySelector('button[id="hangup-button"]').click();
        } catch (e) {
            console.error('[✗] Logout failed:', e);
        }
    }
}

window.Teams = Teams;
window.Browsing = Teams;