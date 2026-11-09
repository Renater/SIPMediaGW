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
        if (key == "s" || key == "q") {
            document.querySelector('button#share-button, button#screenshare-button').click();
            try {
                const shareTabBtn = await this.waitForElement('[data-tid="share-screen-window-or-tab"]', { clickable: true }, 10000);
                shareTabBtn.click();
            } catch (e) {
                // No share picker (e.g. stopping an ongoing share)
                console.log('[INFO] Share picker not shown:', e.message);
            }
        }
    }

    // Returns true once the message is handed to Teams: HTTPLauncher treats any falsy
    // value as a failure (404), and the room macro then sends the message again.
    async sendChat(message) {
        const host = document.querySelector('div[data-tid="ckeditor"]');
        const ed = host && host.ckeditorInstance;
        const send = document.querySelector('button[data-tid="newMessageCommands-send"]');
        if (!ed || !send) {
            console.error('[✗] Chat editor or send button not found');
            return false;
        }
        ed.setData('<p>' + message + '</p>');
        send.click();
        // Teams shows the retry button for about half a second on every successful send:
        // only a button still visible 3 s later is a real failure. Retry once, then stop.
        setTimeout(() => {
            const retry = document.querySelector('button[data-tid="message-failed-retry"]');
            if (retry && retry.getClientRects().length) {
                console.log('[INFO] Chat message failed, retrying once');
                retry.click();
            }
        }, 3000);
        return true;
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