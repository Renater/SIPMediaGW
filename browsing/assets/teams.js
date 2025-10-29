class Teams {
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

    async join() {
        try {
            debugger;
            console.log('[INFO] Waiting for display name input...');
            const nameInput = await this.waitForElement("[data-tid='prejoin-display-name-input']", { visible: true }, 60000);
            const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
            nativeInputValueSetter.call(nameInput, this.displayName);
            nameInput.dispatchEvent(new Event('input', { bubbles: true }));

            const deviceSettings = await this.waitForElement("[id='prejoin-devicesettings-button']", { clickable: true }, 60000);
            deviceSettings.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
            const noiseSuppression = await this.waitForElement("[data-tid='background-suppression-switch']",
                                                               { clickable: true }, 60000);
            noiseSuppression.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));

            console.log('[INFO] Submitting join form...');
            const joinButton = await this.waitForElement("[data-tid='prejoin-join-button']", { clickable: true }, 60000);
            joinButton.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
            console.log('[✓] Join form submitted');
        } catch (error) {
            console.error('[✗] Prejoin process failed:', error);
        }
    }

    async interact(key) {
        if (key == "1")
            document.querySelector('button[id="mic-button"]').click();
        if (key == "2")
            document.querySelector('button[id="video-button"]').click();
        if (key == "3" || key == "c")
            document.querySelector('button[id="chat-button"]').click();
        if (key == "4")
            document.querySelector('button[id="raisehands-button"]').click();
        if (key == "5")
            document.querySelector('button[id="roster-button"]').click();
        if (key == "s")
            document.querySelector('button#share-button, button#screenshare-button').click();
            var logOutBtn = await this.waitForElement('[data-tid="share-screen-window-or-tab"]', { clickable: true }, 10000);
            logOutBtn.click();
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