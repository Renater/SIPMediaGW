class UIHelper {
    constructor() {

        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = window.cssPath;
        document.head.appendChild(link);

        const blocker = document.createElement('div');
        blocker.id = 'blocker';
        blocker.tabIndex = 0;
        document.body.appendChild(blocker);
        this.blocker = blocker;

        // Inject overlay
        const overlay = document.createElement('div');
        overlay.id = "overlay";
        this.overlay = overlay;

        const inner = document.createElement('div');
        inner.className = "overlay-inner";

        overlay.appendChild(inner);
        document.body.appendChild(overlay);
    }

    getDocumentContent(){
        return document;
    }

    setPromptMessage(msg){
        let innerEl = this.overlay.querySelector('.overlay-inner');
        innerEl.innerHTML = msg;

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