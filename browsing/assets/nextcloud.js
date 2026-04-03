class Nextcloud extends UIHelper{
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

    async join() {
        try {
            let startButton1;
            try {
                startButton1 = await this.waitForElement("button[class*='join-call']", { clickable: true });
            } catch (e) {
                console.error('[✗] First Start button not found:', e);
                return;
            }
            startButton1.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
            console.log('[✓] First Start button clicked');
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

            if (document.querySelector('button[class*="submit-button"]')) {
                let submitButton;
                try {
                    submitButton = await this.waitForElement("button[class*='submit-button']", { clickable: true });
                } catch (e) {
                    console.error('[✗] Submit button not found:', e);
                    return;
                }
                submitButton.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                console.log('[✓] Submit button clicked');
            }

            let startButton2;
            try {
                startButton2 = await this.waitForElement("button[class*='join-call action-button']", { clickable: true });
            } catch (e) {
                console.error('[✗] Second Start button not found:', e);
                return;
            }
            startButton2.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
            console.log('[✓] Second Start button clicked');
            this.blockerFocus();
            this.joined = true;
        } catch (error) {
            console.error('[✗] Prejoin process failed:', error);
        }
    }

    interact(key) {
        if (key == "1")
            document.querySelector('[aria-label*="Mute audio"], [aria-label*="Unmute audio"]').click();
        if (key == "2")
            document.querySelector('[aria-label*="Enable video"], [aria-label*="Disable video"]').click();
        if (key == "3" || key == "c") {
            if (document.querySelector('[aria-label*="Open chat"]')) {
                document.querySelector('[aria-label*="Open chat"]').click();
            } else if (document.querySelector('[aria-label*="Close sidebar"]')) {
                document.querySelector('[aria-label*="Close sidebar"]').click();
            }
        }
        if (key == "4")
            document.querySelector('[aria-label*="Raise hand"], [aria-label*="Lower hand"]').click();
        if (key == "s") {
            const shareBtn = document.querySelector('[aria-label*="Enable screensharing"], [aria-label*="Screensharing options"]');
            shareBtn?.click();
            // Click on bouton monitor-icon once it appears
            let monitorBtn = document.querySelector('button.action-button .monitor-icon')?.closest('button');
            if (monitorBtn) {
                monitorBtn.click();
            } else {
                const observer = new MutationObserver(() => {
                    let monitorBtn = document.querySelector('button.action-button .monitor-icon')?.closest('button');
                    if (monitorBtn) {
                        monitorBtn.click();
                        observer.disconnect();
                    }
                });
                observer.observe(document.body, { childList: true, subtree: true });
            }
        }
        if (key == "q") {
            const shareBtn = document.querySelector('[aria-label*="Enable screensharing"], [aria-label*="Screensharing options"]');
            shareBtn?.click();
            setTimeout(() => {
                const stopBtnNow = document.querySelector('button.action-button .monitor-off-icon')?.closest('button');
                stopBtnNow?.click();
            }, 200); 
    }
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

window.Nextcloud = Nextcloud;
window.Browsing = Nextcloud;