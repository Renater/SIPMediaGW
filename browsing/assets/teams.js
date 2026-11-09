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
        this.watchOwnShare();
    }

    // The room's own share (BFCP content, key s) is not drawn in the presenter's
    // page, so it cannot be found in the DOM: the stream Teams asks the browser for
    // is kept instead, to report the share and capture from it.
    watchOwnShare() {
        this.ownShareStream = null;
        const md = navigator.mediaDevices;
        if (!md || !md.getDisplayMedia || md.__gatewayWatched) {
            return;
        }
        const original = md.getDisplayMedia.bind(md);
        md.getDisplayMedia = async (...args) => {
            const stream = await original(...args);
            this.ownShareStream = stream;
            return stream;
        };
        md.__gatewayWatched = true;
    }

    ownShareLive() {
        const s = this.ownShareStream;
        return !!(s && s.getVideoTracks().some(t => t.readyState === 'live'));
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
            screenShare: this.screenShareState()
        };
    }

    // A screen being shared, by anyone: Teams draws the shared content on a canvas
    // (no <video> in the page) with its zoom controls, present only while sharing.
    screenShareState() {
        return document.querySelector('[data-tid="screen-share-zoom-controls"]') !== null || this.ownShareLive();
    }

    async ownShareShot() {
        if (!this.ownShareLive()) {
            return null;
        }
        const video = document.createElement('video');
        video.muted = true;
        video.srcObject = this.ownShareStream;
        try {
            await video.play();
            if (!video.videoWidth) {
                await new Promise(resolve => {
                    const t = setTimeout(resolve, 1500);
                    video.addEventListener('loadeddata', () => { clearTimeout(t); resolve(); }, { once: true });
                });
            }
            const canvas = document.createElement('canvas');
            canvas.width = video.videoWidth || 1280;
            canvas.height = video.videoHeight || 720;
            canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
            return canvas.toDataURL('image/png').split(',')[1];
        } catch (e) {
            console.error('slideShot (own share) failed:', e);
            return null;
        } finally {
            video.srcObject = null;
        }
    }

    // The shared content as a PNG (base64), or null. Teams renders it on a canvas
    // next to the zoom controls; a WebGL canvas may read back empty, which is
    // reported as null (nothing to capture) rather than a blank image.
    async slideShot() {
        try {
            const controls = document.querySelector('[data-tid="screen-share-zoom-controls"]');
            if (!controls) {
                return await this.ownShareShot();
            }
            let source = null;
            for (let p = controls.parentElement, depth = 0; p && depth < 8 && !source; p = p.parentElement, depth++) {
                const candidates = [...p.querySelectorAll('canvas, video')]
                    .filter(e => e.getBoundingClientRect().width > 100);
                candidates.sort((a, b) => b.getBoundingClientRect().width * b.getBoundingClientRect().height
                                        - a.getBoundingClientRect().width * a.getBoundingClientRect().height);
                source = candidates[0] || null;
            }
            if (!source) {
                return null;
            }
            const width = source.videoWidth || source.width || Math.round(source.getBoundingClientRect().width);
            const height = source.videoHeight || source.height || Math.round(source.getBoundingClientRect().height);
            const canvas = document.createElement('canvas');
            canvas.width = width;
            canvas.height = height;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(source, 0, 0, width, height);
            const sample = ctx.getImageData(0, 0, width, height).data;
            let lit = 0;
            for (let i = 0; i < sample.length; i += 4 * 97) {
                if (sample[i + 3] && (sample[i] || sample[i + 1] || sample[i + 2])) {
                    lit++;
                }
            }
            if (lit === 0) {
                console.error('[✗] slideShot: shared content read back empty');
                return null;
            }
            return canvas.toDataURL('image/png').split(',')[1];
        } catch (e) {
            console.error('slideShot failed:', e);
            return null;
        }
    }

    // Same names as Visio (HTTPLauncher, interact, macro); ids from the Teams
    // reactions popup (#reactions-menu-button).
    async reaction(name) {
        const ids = {
            'thumbs-up': 'like-button',
            'red-heart': 'heart-button',
            'clapping-hands': 'applause-button',
            'face-with-tears-of-joy': 'laugh-button',
            'face-with-open-mouth': 'surprised-button'
        };
        if (!(name in ids)) {
            console.error('[✗] Unknown reaction: ' + name);
            return false;
        }
        let button = document.getElementById(ids[name]);
        if (!button) {
            if (!this.clickById('reactions-menu-button')) {
                return false;
            }
            try {
                button = await this.waitForElement('#' + ids[name], { clickable: true }, 2000);
            } catch (e) {
                console.error('[✗] Reaction button not reachable: ' + name);
                return false;
            }
        }
        button.click();
        // close the popup if it stayed open
        if (document.querySelector('[data-tid="reactions-popup"]')) {
            document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
        }
        return true;
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