class EduMeet extends UIHelper {
    constructor(domain, roomName, displayName, lang, prompts, token, audioOnly, dualScreenOn) {
        super();
        this.domain = domain;
        this.roomName = roomName;
        this.displayName = displayName;
        this.lang = lang;
        this.token = token;
        this.joined = false;
    }

    async join() {
        try {
            console.log('[INFO] Waiting for display name input...');
            let nameInput;
            try {
                nameInput = await this.waitForElement("input[type='text']", { visible: true });
            } catch (e) {
                console.error('[✗] Name field not found:', e);
                return;
            }
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            nativeInputValueSetter.call(nameInput, this.displayName);
            nameInput.dispatchEvent(new Event('input', { bubbles: true }));
            console.log('[✓] Name field filled');
            console.log('[INFO] Clicking JOIN...');
            if (!await this._clickJoinUntilInMeeting(120000)) {
                console.error('[✗] In-meeting toolbar not found after JOIN retries');
                return;
            }
            this.blockerFocus();
            this.joined = true;
            console.log('[✓] Joined the meeting');
        } catch (error) {
            console.error('[✗] Prejoin process failed:', error);
        }
    }

    async slideShot() {
        try {
            // Detection in two levels:
            // 1. NAME: every tile (video or avatar) shows the participant
            //    name in a stable MUI chip (.MuiChip-label, same family as
            //    .MuiBadge-badge). When someone shares with the camera on,
            //    the name appears on two tiles (share tile + camera tile).
            // 2. SIZE FALLBACK: if the name appears only once — the sharer's
            //    avatar tile is not rendered while they share with the camera
            //    off — capture when the largest video's long
            //    edge is >= 500px
            const nameMatches = (a, b) => {
                if (!a || !b) return false;
                if (a === b) return true;
                for (const t of [a, b]) {
                    if (t.endsWith('…') || t.endsWith('...')) {
                        const base = t.replace(/[.…]+$/, '').trim();
                        const other = (t === a) ? b : a;
                        if (base.length >= 4 && other.startsWith(base)) return true;
                    }
                }
                return false;
            };

            const tileName = (video) => {
                let el = video.parentElement;
                for (let k = 0; k < 6 && el; k++) {
                    const chip = el.querySelector('.MuiChip-label');
                    if (chip) return chip.textContent.trim();
                    el = el.parentElement;
                }
                return null;
            };

            const findShareVideo = () => {
                const candidate = [...document.querySelectorAll('video')]
                    .filter(v => v.videoWidth > 0)
                    .sort((a, b) => (b.videoWidth * b.videoHeight) - (a.videoWidth * a.videoHeight))[0];
                if (!candidate) return null;
                const name = tileName(candidate);
                if (name) {
                    const count = [...document.querySelectorAll('.MuiChip-label')]
                        .filter(c => nameMatches(name, c.textContent.trim())).length;
                    if (count >= 2) return candidate;
                }
                if (Math.max(candidate.videoWidth, candidate.videoHeight) >= 500) return candidate;
                return null;
            };

            const wait = ms => new Promise(res => setTimeout(res, ms));
            let video = findShareVideo();
            const maxWait = 2000;
            const step = 100;
            let waited = 0;
            while (!video && waited < maxWait) {
                await wait(step);
                waited += step;
                video = findShareVideo();
            }
            if (!video) {
                return null;
            }
            // await the video to have valid dimensions
            if (!video.videoWidth || !video.videoHeight) {
                await new Promise(resolve => {
                    const onLoaded = () => {
                        video.removeEventListener('loadeddata', onLoaded);
                        resolve();
                    };
                    // fallback timeout if the event doesn't arrive
                    const t = setTimeout(() => {
                        video.removeEventListener('loadeddata', onLoaded);
                        resolve();
                    }, 1000);
                    video.addEventListener('loadeddata', onLoaded);
                });
            }
            const width = video.videoWidth || video.clientWidth || 640;
            const height = video.videoHeight || video.clientHeight || Math.round(width * 9 / 16);
            const canvas = document.createElement('canvas');
            canvas.width = width;
            canvas.height = height;
            const ctx = canvas.getContext('2d');

            ctx.drawImage(video, 0, 0, width, height);

            const dataURL = canvas.toDataURL('image/png');
            if (!dataURL) {
                return null;
            }
            // return the base64 part (without "data:image/png;base64,")
            return dataURL.split(',')[1];
        } catch (e) {
            console.error("slideShot failed:", e);
            return null;
        }
    }

    // Click JOIN and keep retrying while the app is still on the pre-join screen.
    // The first click can be swallowed if edumeet has not finished initializing;
    // the JOIN button disappearing is the reliable signal the click was accepted,
    // so we only re-click while the JOIN button is still present.
    async _clickJoinUntilInMeeting(timeout) {
        const deadline = Date.now() + timeout;
        while (Date.now() < deadline) {
            if (this._findAriaButton(['LEAVE', 'QUITTER'])) {
                return true;
            }
            const joinButton = [...document.querySelectorAll('button')]
                .find(b => (b.innerText || b.textContent || '').trim().toUpperCase().includes('JOIN'));
            if (joinButton) {
                joinButton.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                console.log('[~] JOIN clicked, waiting for the in-meeting toolbar...');
            }
            await new Promise(res => setTimeout(res, 2000));
        }
        return !!this._findAriaButton(['LEAVE', 'QUITTER']);
    }

    // Match a button by its aria-label against a list of localized labels
    // (EN/FR), case-insensitively. Returns the button or null.
    _findAriaButton(labels) {
        return [...document.querySelectorAll('button')].find(b =>
            labels.includes((b.getAttribute('aria-label') || '').trim().toUpperCase()));
    }

    _clickAria(labels) {
        for (const label of labels) {
            const btn = [...document.querySelectorAll('button')]
                .find(b => (b.getAttribute('aria-label') || '').toUpperCase().includes(label.toUpperCase()));
            if (btn) {
                btn.click();
                console.log('[✓] Toggled: ' + label);
                return true;
            }
        }
        console.warn('[!] No matching button for: ' + labels.join(' / '));
        return false;
    }

    interact(key) {
        if (key == '1') {
            this._clickAria(['audio']);
        } else if (key == '2') {
            this._clickAria(['video', 'vidéo']);
        } else if (key == '3' || key == 'c') {
            this._clickAria(['chat']);
        } else if (key == '4') {
            this._clickAria(['hand', 'main']);
        } else if (key == '5') {
            this._clickAria(['participants']);
        } else if (key == 's' || key == 'q') {
            this._clickAria(['screen', 'écran']);
        } else {
            console.warn('[!] Unknown DTMF key: ' + key);
        }
    }

    getParticipantNum() {
        const btn = this._findAriaButton(['SHOW PARTICIPANTS', 'HIDE PARTICIPANTS',
                                          'AFFICHER LES PARTICIPANTS', 'MASQUER LES PARTICIPANTS']);
        if (!btn) return null;
        const badge = btn.querySelector('.MuiBadge-badge');
        if (!badge) return null;
        const n = parseInt(badge.textContent, 10);
        return Number.isNaN(n) ? null : n;
    }

    hasLeft() {
        return this.joined && !this._findAriaButton(['LEAVE', 'QUITTER']);
    }

    async leave() {
        try {
            const deadline = Date.now() + 20000;
            while (Date.now() < deadline) {
                if (!this._findAriaButton(['LEAVE', 'QUITTER'])) {
                    console.log('[✓] Left the meeting');
                    return;
                }
                // The confirm dialog is the one that holds a YES/OUI button.
                // Other dialogs (e.g. settings) may be open at the same time,
                // so scan all of them instead of taking the first match in the DOM.
                const yes = [...document.querySelectorAll('.MuiDialog-root, [role="dialog"]')]
                    .flatMap(d => [...d.querySelectorAll('button')])
                    .find(b => ['YES', 'OUI'].includes((b.innerText || '').trim().toUpperCase()));
                if (yes) {
                    yes.click();
                    console.log('[✓] Leave confirmed');
                    return;
                }
                // No confirm dialog yet: (re)click Leave. The click can be
                // swallowed like the JOIN one, so retry while the button is
                // still present.
                const leaveBtn = this._findAriaButton(['LEAVE', 'QUITTER']);
                if (leaveBtn) {
                    leaveBtn.click();
                    console.log('[~] Leave clicked, waiting for the confirm dialog...');
                }
                await new Promise(res => setTimeout(res, 1500));
            }
            console.warn('[✗] Leave failed: confirm dialog did not appear in time');
        } catch (e) {
            console.error('[✗] Leave failed:', e);
        }
    }

    async sendChat(message) {
        try {
            const chatInputVisible = [...document.querySelectorAll("input[type='text']")]
                .some(e => e.offsetParent !== null);
            if (!chatInputVisible) {
                const chatBtn = this._findAriaButton(['SHOW CHAT', 'HIDE CHAT',
                                                      'AFFICHER LE CHAT', 'MASQUER LE CHAT']);
                if (!chatBtn) {
                    console.warn('[!] Chat button not found');
                    return false;
                }
                chatBtn.click();
            }
            const input = await this.waitForElement("input[type='text']", { visible: true }, 5000);
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            nativeInputValueSetter.call(input, message);
            input.dispatchEvent(new Event('input', { bubbles: true }));
            const sendBtn = this._findAriaButton(['ENTER CHAT MESSAGE...', 'ENTRER UN MESSAGE']);
            if (!sendBtn) {
                console.warn('[!] Chat send button not found');
                return false;
            }
            sendBtn.click();
            return true;
        } catch (e) {
            console.warn('[!] sendChat failed:', e);
            return false;
        }
    }
}

window.EduMeet = EduMeet;
window.Browsing = EduMeet;
