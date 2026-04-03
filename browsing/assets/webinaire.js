class Webinaire extends UIHelper {
    constructor(domain, roomName, displayName, lang, prompts, token, audioOnly) {
        super();
        this.domain = domain;
        this.roomName = roomName;
        this.displayName = displayName;
        this.lang = lang;
        this.token = token;
        this.joined = false;
        this.passwordPrompt = JSON.parse(prompts)[lang]['password'];
    }

    async tryClickWhileVisible(selector, retries = 5, delay = 1000) {
        for (let i = 0; i < retries; i++) {
            try {
                let el;
                try {
                    el = await this.waitForElement(selector, { clickable: true }, delay);
                } catch (e) {
                    console.warn(`[!] waitForElement failed for ${selector}: ${e.message}`);
                    continue;
                }
                el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                console.log(`[~] Click ${i + 1}/${retries} on ${selector}`);

                await new Promise(res => setTimeout(res, delay));

                const stillVisible = document.querySelector(selector);
                if (!stillVisible || stillVisible.offsetParent === null) {
                    console.log(`[✓] ${selector} is no longer visible after click`);
                    return true;
                }
            } catch (e) {
                console.warn(`[!] Attempt ${i + 1} failed for ${selector}: ${e.message}`);
            }
        }
        console.warn(`[✗] Failed to click ${selector} after ${retries} attempts`);
        return false;
    }

    async closeParticipantsPanelOnEnter() {
        if (this._participantsClosedOnEnter) return;
        try {
            // wait until the main UI is ready
            const usersToggle = await this.waitForElement('[accesskey="U"]', { clickable: true }, 15000);
            usersToggle.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
            this._participantsClosedOnEnter = true;
            console.log("[✓] Participants panel toggled (closed) on enter");
        } catch (e) {
            console.warn("[!] Could not close participants panel on enter:", e?.message || e);
        }
    }

    async join() {
        try {
            console.log('[INFO] Waiting for display name input...');
            let nameInput;
            try {
                nameInput = await this.waitForElement('#fullname', { visible: true });
            } catch (e) {
                console.error('[✗] Name field not found:', e);
                return;
            }
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            nativeInputValueSetter.call(nameInput, this.displayName);
            nameInput.dispatchEvent(new Event('input', { bubbles: true }));
            console.log('[✓] Name field detected and filled');
            console.log('[INFO] Submitting join form...');
            let joinButton;
            try {
                joinButton = await this.waitForElement("button[type='submit']", { clickable: true });
            } catch (e) {
                console.error('[✗] Join button not found:', e);
                return;
            }
            joinButton.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
            this.blockerFocus();
            this.joined = true;
            console.log('[✓] Join form submitted');
        } catch (error) {
            console.error('[✗] Prejoin process failed:', error);
        }
    }

    async startVideo() {
        try {
            console.log('[INFO] Activating camera...');
            let cameraBtn;
            try {
                cameraBtn = await this.waitForElement("[data-test='joinVideo']", { clickable: true });
            } catch (e) {
                console.error('[✗] Camera button not found:', e);
                return;
            }
            cameraBtn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
            console.log('[✓] Camera button clicked');

            console.log('[INFO] Setting video quality...');
            const captureVideoQuality = "medium"; // or "low", "high"
            let qualityDropdown;
            try {
                qualityDropdown = await this.waitForElement("#setQuality", { clickable: true });
            } catch (e) {
                console.error('[✗] Quality dropdown not found:', e);
                return;
            }
            qualityDropdown.value = captureVideoQuality;
            qualityDropdown.dispatchEvent(new Event("change", { bubbles: true }));
            console.log(`[✓] Video quality set: ${captureVideoQuality}`);

            console.log('[INFO] Starting webcam sharing...');
            await this.tryClickWhileVisible('[data-test="startSharingWebcam"]');
        } catch (error) {
            console.error('[✗] startVideo failed:', error);
        }
    }

    async startAudio() {
        console.log('[INFO] Enabling microphone...');
            let micDetails;
            try {
                micDetails = await this.waitForElement("[data-test='audioModal']", { visible: true });
            } catch (e) {
                console.error('[✗] Microphone modal not found:', e);
                return;
            }
            micDetails.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
            await this.tryClickWhileVisible('[data-test="joinEchoTestButton"]');
    }

    async browse() {
        try {
            await this.startAudio();
            const acceptSelector = "[aria-label='Accept recording and continue']";
            const acceptEl = document.querySelector(acceptSelector);
            if (acceptEl) {
                console.log('[INFO] Waiting for recording acceptance (someone should trigger it)...');
                const timeoutMs = 120000; // safety timeout
                const pollMs = 500;
                const start = Date.now();
                while (Date.now() - start < timeoutMs) {
                    const el = document.querySelector(acceptSelector);
                    if (!el) break;
                    const style = window.getComputedStyle(el);
                    const visible = style.display !== 'none' && style.visibility !== 'hidden' && el.offsetHeight > 0 && el.offsetWidth > 0;
                    if (!visible) break;
                    await new Promise(res => setTimeout(res, pollMs));
                }
            }
            await this.startVideo();
            document.querySelector('[accesskey="M"]').click();
            await this.closeParticipantsPanelOnEnter();
        } catch (error) {
            console.error('[✗] Join process failed:', error);
        } finally {
            this.joined = true;
        }
    }

    interact(key) {
        if (key == "1")
            document.querySelector('[accesskey="M"]').click();
        if (key == "2")
            if (document.querySelector("[data-test='joinVideo']")) {
                this.startVideo();
            }
            else if (document.querySelector("[data-test='leaveVideo']")) {
                document.querySelector("[data-test='leaveVideo']").click();
            }
        if (key == "3" || key == "c")
            document.querySelector('[accesskey="P"]').click();
        if (key == "4")
            document.querySelector('[accesskey="R"]').click();
        if (key == "5")
            document.querySelector('[accesskey="U"]').click();
        if (key == "6")
            document.querySelector('[aria-label="Accept recording and continue"]').click();
            if (document.querySelector("[data-test='joinAudio']")) {
                this.startAudio();
            }
        if (key == "s" || key == "q")
            document.querySelector("[data-test='startScreenShare']").click();
    }

    async typeText(text) {
        const input = document.querySelector('#message-input');
        const lastValue = input.value;
        input.value = text;
        const tracker = input._valueTracker;
        if (tracker) {
            tracker.setValue(lastValue);
        }
        input.dispatchEvent(new Event('input', { bubbles: true }));
        document.querySelector('[data-test="sendMessageButton"]').click();
    }
    async leave() {
        console.log('[INFO] Leave the meeting room');
        try {
            var leaveBtn = await this.waitForElement('[data-test="leaveMeetingDropdown"]', { clickable: true }, 10000);
            leaveBtn.click();
            var logOutBtn = await this.waitForElement('[data-test="directLogoutButton"]', { clickable: true }, 10000);
            logOutBtn.click();
        } catch (e) {
            console.error('[✗] Logout failed:', e);
        }
    }
}

window.Webinaire = Webinaire;
window.Browsing = Webinaire;