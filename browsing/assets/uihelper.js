class UIHelper {
    constructor() {
        const blocker = document.createElement('div');
        blocker.id = 'blocker';
        blocker.tabIndex = 0;
        blocker.style.position = 'fixed';
        blocker.style.top = '0';
        blocker.style.left = '0';
        blocker.style.width = '100vw';
        blocker.style.height = '100vh';
        blocker.style.zIndex = '9999';
        document.body.appendChild(blocker);
        this.blocker = blocker;

       // Inject overlay for password prompt
        const overlay = document.createElement('div');
        overlay.style.display = "none";
        overlay.style.position = "fixed";
        overlay.style.top = "0";
        overlay.style.left = "0";
        overlay.style.width = "100vw";
        overlay.style.height = "100vh";
        overlay.style.background = "rgba(0,0,0,0.45)";
        overlay.style.zIndex = "9999";
        overlay.style.alignItems = "center";
        overlay.style.justifyContent = "center";
        overlay.style.flexDirection = "column";
        overlay.style.fontFamily = "inherit";
        overlay.style.fontSize = "1.5rem";
        overlay.style.color = "#1b2640";
        overlay.style.textAlign = "center";
        this.overlay = overlay;

        const inner = document.createElement('div');
        inner.style.background = "white";
        inner.style.padding = "2rem 2.5rem";
        inner.style.borderRadius = "12px";
        inner.style.boxShadow = "0 4px 24px rgba(0,0,0,0.15)";
        inner.textContent = "Enter the password and press # to validate";

        overlay.appendChild(inner);
        document.body.appendChild(overlay);
    }

    getDocumentContent(){
        return document;
    }

    async waitForElement(selector, { visible = false, clickable = false } = {}, timeout = 20000) {
        const start = Date.now();
        return new Promise((resolve, reject) => {
            const interval = setInterval(() => {
            console.warn("Looking for a password input");
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
        this.blocker.focus();
        this.blocker.addEventListener('blur', () => {
            setTimeout(() => this.blocker.focus(), 0);
        });
    }

}

window.UIHelper = UIHelper;