class Bigbluebutton {
    constructor(domain, roomName, displayName, lang, token, audioOnly) {
        this.domain = domain;
        this.roomName = roomName;
        this.displayName = displayName;
        this.lang = lang;
        this.token = token;
    }

    // Utility: Wait for an element to be clickable
    async waitForElement(selector, { visible = false, clickable = false } = {}, timeout = 20000) {
        const start = Date.now();

        return new Promise((resolve, reject) => {
            const interval = setInterval(() => {
                const el = document.querySelector(selector);
                if (!el) return;
                const style = window.getComputedStyle(el);
                const isVisible = style.display !== 'none' && style.visibility !== 'hidden' && el.offsetHeight > 0 && el.offsetWidth > 0;
                const isEnabled = !el.disabled;
                if (
                    (!visible || isVisible) &&
                    (!clickable || (isVisible && isEnabled))
                ) {
                    clearInterval(interval);
                    resolve(el);
                }
                if (Date.now() - start > timeout) {
                    clearInterval(interval);
                    reject(new Error(`Timeout: ${selector} not matching criteria`));
                }
            }, 100);
        });
    }

    async tryClickWhileVisible(selector, retries = 5, delay = 1000) {
        for (let i = 0; i < retries; i++) {
            try {
                const el = await this.waitForElement(selector, { clickable: true }, delay);
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

    async join() {
        try {
            console.log('[INFO] Waiting for display name input...');
            const nameInput = await this.waitForElement('#joinFormName', { visible: true });
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            nativeInputValueSetter.call(nameInput, this.displayName);
            nameInput.dispatchEvent(new Event('input', { bubbles: true }));
            console.log('[✓] Name field detected and filled');
            console.log('[INFO] Submitting join form...');
            const joinButton = await this.waitForElement("button[type='submit']", { clickable: true });
            joinButton.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
            console.log('[✓] Join form submitted');
        } catch (error) {
            console.error('[✗] Prejoin process failed:', error);
        }
    }

    async startVideo() {
        console.log('[INFO] Activating camera...');
        const cameraBtn = await this.waitForElement("[data-test='joinVideo']", { clickable: true });
        cameraBtn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
        console.log('[✓] Camera button clicked');

        console.log('[INFO] Setting video quality...');
        const captureVideoQuality = "medium"; // or "low", "high"
        const qualityDropdown = await this.waitForElement("#setQuality", { clickable: true });
        qualityDropdown.value = captureVideoQuality;
        qualityDropdown.dispatchEvent(new Event("change", { bubbles: true }));
        console.log(`[✓] Video quality set: ${captureVideoQuality}`);

        console.log('[INFO] Starting webcam sharing...');
        await this.tryClickWhileVisible('[data-test="startSharingWebcam"]');
    }

    async browse() {
        try {
            console.log('[INFO] Enabling microphone...');
            const micDetails = await this.waitForElement("[data-test='audioModal']", { visible: true });
            micDetails.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
            await this.tryClickWhileVisible('[data-test="joinEchoTestButton"]');

            console.log('[INFO] Closing session details modal...');
            var sessionDetails = await this.waitForElement("[data-test='sessionDetailsModal']", { visible: true });
            var closeBtn = sessionDetails.querySelector("[data-test='closeModal']");
            closeBtn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
            console.log('[✓] Modal closed');

            await this.startVideo();

        } catch (error) {
            console.error('[✗] Join process failed:', error);
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
        if (key == "s")
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

window.Bigbluebutton = Bigbluebutton;
window.Browsing = Bigbluebutton;