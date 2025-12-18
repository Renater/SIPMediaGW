class UIHelper {
    constructor() {
        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = window.cssPath;
        document.head.appendChild(link);

        // Inject overlay
        const overlay = document.createElement('div');
        overlay.id = "overlay";
        overlay.style.display = "none";
        this.overlay = overlay;

        // Overlay inner (prompt + input)
        const inner = document.createElement('div');
        inner.className = "overlay-inner";

        // Message container (will be set by setPromptMessage)
        const messageDiv = document.createElement('div');
        messageDiv.className = "overlay-message";
        inner.appendChild(messageDiv);

        // Password input
        const passwordInput = document.createElement('input');
        passwordInput.type = "password";
        passwordInput.className = "overlay-password-input";
        passwordInput.autocomplete = "off";
        passwordInput.readOnly = true; // JS handles input logic

        inner.appendChild(passwordInput);
        overlay.appendChild(inner);
        document.body.appendChild(overlay);

        this.passwordInput = passwordInput;
        this.messageDiv = messageDiv;
    }

    getDocumentContent(){
        return document;
    }

    setPromptMessage(msg){
        if (this.messageDiv) {
            this.messageDiv.innerHTML = msg;
        }
    }

    async waitForElement(selector, { visible = false, clickable = false } = {}, timeout = 20000) {
        const start = Date.now();
        return new Promise((resolve, reject) => {
            const interval = setInterval(() => {
                if (Date.now() - start > timeout) {
                    clearInterval(interval);
                    reject(new Error(`Timeout: ${selector} not matching criteria`));
                }
                let el = null;
                let root = this.getDocumentContent();
                el = root.querySelector(selector);
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
            }, 100);
        });
    }

    blockerFocus(){
        const blocker = document.createElement('div');
        blocker.id = 'blocker';
        blocker.tabIndex = 0;
        document.body.appendChild(blocker);
        this.blocker = blocker;
        this.blocker.focus();
        this.blocker.addEventListener('blur', () => {
            setTimeout(() => this.blocker.focus(), 0);
        });
    }

    setPasswordDisplay(pwd) {
        if (this.passwordInput) {
            this.passwordInput.value = '*'.repeat(pwd.length);
        }
    }
}

window.UIHelper = UIHelper;