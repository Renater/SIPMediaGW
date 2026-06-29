class Visio extends UIHelper{
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
            this.blockerFocus();
            this.joined = true;
        } catch (error) {
            console.error('[✗] Prejoin process failed:', error);
        }
    }
    async slideShot() {
        try {
            const selector = "video.lk-participant-media-video[data-lk-source='screen_share']";
            // short wait for the element to appear if necessary
            const wait = ms => new Promise(res => setTimeout(res, ms));
            let video = document.querySelector(selector);
            const maxWait = 2000;
            const step = 100;
            let waited = 0;
            while (!video && waited < maxWait) {
                await wait(step);
                waited += step;
                video = document.querySelector(selector);
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
        if (key == "s" || key == "q") {
            document.querySelector('[data-attr*="controls-screenshare"]').click();

            const interval = setInterval(() => {
                const tile = document.querySelector('[data-lk-source="screen_share"]');
                if (!tile) return;

                const ignoreBtn = [...tile.querySelectorAll('button')]
                    .find(btn => /ignore/i.test(btn.textContent));

                if (ignoreBtn) {
                    clearInterval(interval);
                    ignoreBtn.click();
                }
            }, 200);

            setTimeout(() => clearInterval(interval), 5000); // sécurité
        }
    }
    sendChat(message) {
        const textarea = document.querySelector('textarea');
        if (!textarea) {
            return;
        }
        // Setter natif compatible React
        const nativeSetter = Object.getOwnPropertyDescriptor(
            window.HTMLTextAreaElement.prototype,
            'value'
        ).set;
        nativeSetter.call(textarea, message);
        // Events React
        textarea.dispatchEvent(new Event('input', { bubbles: true }));

        textarea.dispatchEvent(new KeyboardEvent('keydown', {
            key: 'Enter',
            code: 'Enter',
            keyCode: 13,
            which: 13,
            bubbles: true
        }));
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