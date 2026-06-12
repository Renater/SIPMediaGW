class Menu {
    constructor(menu, lang) {
        debugger;
        this.meeting = window.meeting;
        this.overlayTimeouts = {};
        this.img = {
            icon: null,
            dtmf: null,
            icons: {},
        };
        this.lang = lang;
        this.menu = menu;
    }

    fetchWithTimeout(resource, options = {}, timeout = 5000, onError = null) {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => {
            controller.abort();
            if (onError) onError("timeout");
        }, timeout);

        options = { ...options, signal: controller.signal };

        return fetch(resource, options)
            .then((response) => {
                clearTimeout(timeoutId);
                return response;
            })
            .catch((err) => {
                if (onError) onError(err);
                throw err;
            });
    }

    createOverlayImage(imgKey, bt, left, timeout = 0) {
        var imId = "menu_" + imgKey;
        let existing = document.getElementById(imId);
        if (!existing) {
            const img = document.createElement("img");
            img.id = imId;
            img.src = this.img[imgKey];
            img.style.position = "fixed";
            img.style.bottom = bt;
            img.style.left = left;
            img.style.zIndex = "9999";
            let wrapper = document.getElementById("wrapper")
            if (!wrapper) {
                wrapper = document.createElement("div");
                wrapper.id = "wrapper";
            }
            wrapper.appendChild(img);
        } else {
            existing.style.display = "block";
        }
        if (timeout > 0) {
            setTimeout(() => this.hideOverlayImage(imId), timeout);
        }
    }

    async createOverlayMenu(imgKey, bt, left, timeout = 0) {
        var menuId = "menu_" + imgKey;
        let existing = document.getElementById(menuId);
        if (!existing) {
            const menu = document.createElement("div");
            menu.id = menuId;
            menu.style.position = "fixed";
            menu.style.backgroundColor = "white";
            menu.style.borderRadius = "10px";
            menu.style.bottom = bt;
            menu.style.left = left;
            menu.style.zIndex = "9999";
            menu.style.padding = "10px";
            document.body.appendChild(menu);
            menu.appendChild(this.createMenuContainer());
        } else {
            existing.style.display = "block";
        }
        if (timeout > 0) {
            setTimeout(() => this.hideOverlayMenu(menuId), timeout);
        }
    }

    createMenuContainer() {
        const container = document.createElement("div");
        Object.assign(container.style, {
            backgroundColor: "white",
            borderRadius: "10px",
            border: "1px solid black",
            color: "black",
            padding: "15px",
            boxShadow:
                "0 4px 6px -1px rgba(0,0,0,0.1),0 2px 4px -2px rgba(0,0,0,0.1)",
        });

        const column = document.createElement("div");
        Object.assign(column.style, {
            display: "flex",
            flexDirection: "column",
            gap: "10px",
        });

        const dtmfOptions = this.getDtmfOptions();
        dtmfOptions.forEach((option) => {
            column.appendChild(this.createFlexLine(option));
        });

        container.appendChild(column);
        return container;
    }

    createFlexLine(option) {
        const lang = this.lang || "fr";
        const line = document.createElement("div");
        Object.assign(line.style, {
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
            gap: "20px",
        });

        const img = document.createElement("img");
        img.src = this.img.icons[option.icon];
        img.style.width = "25px";

        const label = document.createElement("span");
        label.textContent = option[lang];
        label.style.flexGrow = "1";

        const badge = document.createElement("span");
        badge.textContent = option.dtmf;
        Object.assign(badge.style, {
            backgroundColor: "#000091",
            color: "white",
            fontWeight: "bold",
            width: "20px",
            height: "20px",
            borderRadius: "50%",
            display: "flex",
            justifyContent: "center",
            alignItems: "center",
        });

        line.appendChild(img);
        line.appendChild(label);
        line.appendChild(badge);

        return line;
    }

    getDtmfOptions() {
        return this.menu && Array.isArray(this.menu.options) ? this.menu.options : [];
    }

    showOverlayMenu(id) {
        const menu = document.getElementById(id);
        if (menu) {
            menu.style.display = "block";
        }
    }

    hideOverlayMenu(id) {
        const menu = document.getElementById(id);
        if (menu) {
            menu.style.display = "none";
        }
    }

    toggleOverlayMenu(id, timeout = 5000) {
        const menu = document.getElementById(id);
        if (menu && menu.style.display == "block") {
            this.hideOverlayMenu(id);
            clearTimeout(this.overlayTimeouts[id]);
        } else {
            this.showOverlayMenu(id, 0);
            if (this.overlayTimeouts[id]) {
                clearTimeout(this.overlayTimeouts[id]);
            }
            this.overlayTimeouts[id] = setTimeout(() => {
                this.hideOverlayMenu(id);
                delete this.overlayTimeouts[id];
            }, timeout);
        }
    }

    interact(key) {
        if (key == "#") {
            this.toggleOverlayMenu("menu_dtmf", 5000);
        }
        else if(key == "*"){
            this.toggleOverlayImage('menu_icon', 5000);
        }
        else {
            this.meeting.interact(key);
        }
    }

    showOverlayImage(id) {
        const img = document.getElementById(id);
        if (img) {
            img.style.display = "block";
        }
    }

    hideOverlayImage(id) {
        const img = document.getElementById(id);
        if (img) {
            img.style.display = "none";
        }
    }

    toggleOverlayImage(id, timeout = 5000) {
        const img = document.getElementById(id);
        if (img && img.style.display == "block") {
            this.hideOverlayImage(id);
            clearTimeout(this.overlayTimeouts[id]);
        } else {
            this.showOverlayImage(id, 0);
            if (this.overlayTimeouts[id]) {
                clearTimeout(this.overlayTimeouts[id]);
            }
            this.overlayTimeouts[id] = setTimeout(() => {
                this.hideOverlayImage(id);
                delete this.overlayTimeouts[id];
            }, timeout);
        }
    }

    async show() {
        this.createOverlayImage("icon", "20px", "20px", 3000);
        console.log("Menu config loaded:", this.config);
        this.createOverlayMenu("dtmf", "10px", "10px", 5000);

        try {
            document.addEventListener(
                "keydown",
                (e) => {
                    const key = e.key;
                if ((key >= '0' && key <= '9') ||
                     key === '#' || key === 's' || key === 'q' || key === '*') {
                    e.preventDefault();
                    this.interact(key);
                    }
                },
                { capture: true }
            );
        } catch (err) {
            console.error("Error during Menu setup:", err);
            onError(err);
        }
    }
}

window.updateQrCode = function() {
    pairingInfo = window.pairingInfo;
    if (pairingInfo) {
        qrB64 = pairingInfo.qrCodeB64;
        pairingCode = pairingInfo.pairingCode;
        pairingUrl = pairingInfo.pairingUrl;
    }

    // fallback: update existing elements or create them with explicit styles
    let container = document.getElementById('qr-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'qr-container';
        Object.assign(container.style, {
            position: 'fixed',
            right: '50px',
            bottom: '70px',
            zIndex: '10001',
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center'
        });
    }

    let qrDiv = document.getElementById('qr-overlay');
    if (!qrDiv) {
        qrDiv = document.createElement('div');
        qrDiv.id = 'qr-overlay';
        Object.assign(qrDiv.style, {
            background: 'rgba(255,255,255,0.92)',
            padding: '8px',
            borderRadius: '8px',
            boxShadow: '0 2px 8px rgba(0,0,0,0.2)',
            marginBottom: '10px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
        });
        container.appendChild(qrDiv);
    }

    let img = qrDiv.querySelector('img');
    if (!img) {
        img = document.createElement('img');
        qrDiv.appendChild(img);
    }
    img.src = 'data:image/png;base64,' + qrB64;
    Object.assign(img.style, {
        width: '100px',
        height: '100px',
        display: 'block'
    });

    let info = document.getElementById('pairing-info');
    if (!info && (pairingCode || pairingUrl)) {
        info = document.createElement('div');
        info.id = 'pairing-info';
        Object.assign(info.style, {
            background: '#ffffff',
            padding: '8px',
            borderRadius: '8px',
            boxShadow: '0 2px 8px rgba(0,0,0,0.2)',
            color: '#2a3550',
            fontSize: '1.125rem',
            lineHeight: '1.4',
            textAlign: 'center'
        });
        container.appendChild(info);
    }

    if (info) {
        const urlHtml = pairingUrl ? `<a href="${pairingUrl}" target="_blank">${pairingUrl}</a>` : '';
        info.innerHTML = pairingCode
            ? `Code: ${pairingCode}${urlHtml ? '<br/>(' + urlHtml + ')' : ''}`
            : (urlHtml ? `(${urlHtml})` : '');
    }

    // Ensure visible and on top
    container.style.display = 'flex';
    container.style.zIndex = '10001';
    debugger;
    if (!document.body.contains(container)) {
        if (window.menu) {
            const menuDtmf = document.getElementById('menu_dtmf');
            menuDtmf.appendChild(container);
        }
        else{
            document.body.appendChild(container);
        }
    }
};

window.Menu = Menu;