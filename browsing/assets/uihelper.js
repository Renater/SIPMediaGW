class UIHelper {
    constructor() {}
    async waitForElement(selector, { visible = false, clickable = false } = {}, timeout = 20000, root = document) {
            const start = Date.now();
            return new Promise((resolve, reject) => {
                    const interval = setInterval(() => {
                    console.warn("Looking for a password input");
                    if (Date.now() - start > timeout) {
                            clearInterval(interval);
                            reject(new Error(`Timeout: ${selector} not matching criteria`));
                    }
                    const el = root.querySelector(selector);
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
}

window.UIHelper = UIHelper;