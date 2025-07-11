class Visio {
    constructor(domain, roomName, displayName, lang, token) {
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
            const nameInput = await this.waitForElement("input[type='text']", { visible: true });
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

    interact(key) {
        if (key == "1")
            document.querySelector('[aria-label*="Ctrl+d"]').click();
        if (key == "2")
            document.querySelector('[aria-label*="Ctrl+e"]').click();
        if (key == "3" || key == "c")
            document.querySelector('button[data-attr*="controls-chat-closed"], button[data-attr*="controls-chat-open"]').click();
        if (key == "4")
            document.querySelector('button[data-attr*="controls-hand-raise"], button[data-attr*="controls-hand-lower"]').click();
        if (key == "5")
            document.querySelector('button[data-attr*="controls-participants-closed"], button[data-attr*="controls-participants-open"]').click();
        if (key == "s")
            document.querySelector('[data-attr*="controls-screenshare"]').click();
    }

    async leave() {
        console.log('[INFO] Leave the meeting room');
        try {
            document.querySelector('[data-attr*="controls-leave"]').click();
        } catch (e) {
            console.error('[✗] Logout failed:', e);
        }
    }
}

window.Visio = Visio;
window.Browsing = Visio;