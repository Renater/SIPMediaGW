class Teams extends UIHelper {
    constructor(domain, roomName, displayName, lang, token, audioOnly) {
        super();
        this.domain = domain;
        this.roomName = roomName;
        this.displayName = displayName;
        this.lang = lang;
        this.token = token;
        this.joinded = false;
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
            this.blockInteract()
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