class Visio extends UIHelper{
    constructor(domain, roomName, displayName, lang, token, audioOnly) {
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
            console.log('[✓] Join form submitted');
            this.joined = true;
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