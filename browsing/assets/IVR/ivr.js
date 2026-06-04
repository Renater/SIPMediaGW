import { Room } from './room.js';

const messages = {
    fr: {
        valid: code => `Code validé : ${code}`,
        invalid: error => `Le code n'est pas valide ('${error}')`,
        incomplete: (count, expected) => `Le code est trop court (${count}/${expected})`,
        error: reason => `Erreur : ${reason}`,
        chosenDomain: (id, name) => `Plateforme sélectionnée (${id}) : ${name}`,
        confirmContinue: "— appuyez sur '#' pour continuer"
    },
    en: {
        valid: code => `Code validated: ${code}`,
        invalid: error => `The code is not valid ('${error}')`,
        incomplete: (count, expected) => `The code is too short (${count}/${expected})`,
        error: reason => `Error: ${reason}`,
        chosenDomain: (id, name) => `Platform selected (${id}): ${name}`,
        confirmContinue: "— press '#' to continue"
    }
};

document.getElementById("digits").addEventListener("beforeinput", e => e.preventDefault());

fetch("../config.json")
    .then(res => res.json())
    .then(config => initIVR(config))
    .catch(err => console.error("Failed to load config.json", err));

function initIVR(config) {
    const messageEl = document.getElementById("message");
    const digitsEl = document.getElementById("digits");
    const statusEl = document.getElementById("status");
    const domainsEl = document.getElementById("domains");

    const prompts = config['ivr_prompts'];
    const lang = config['lang'] || 'fr';
    const expectedLength = parseInt(config['min_ivr_digit_length'], 10) || 0;
    const domains = parseDomains(config['webrtc_domains']);

    let inputDigits = [];
    let stage = "domain"; // 'domain' -> 'room'
    let selectedDomain = null;
    let pendingRoomId = null;
    let currentAudio = null;
    let waitingConfirm = null; // { proceed: Function, roomId: string } when mapping failed

    function parseDomains(raw) {
        const dict = {};
        let index = 1;
        for (const [key, obj] of Object.entries(raw)) {
            dict[index] = { id: index, key, name: obj.name, domain: obj.domain };
            index++;
        }
        return dict;
    }

    function updateDisplay() {
        const filled = inputDigits.join(' ');
        let empty = "";
        if (stage === "domain") empty = inputDigits.length === 0 ? "_" : "";
        else if (stage === "room") empty = Array(Math.max(0, expectedLength - inputDigits.length)).fill('_').join(' ');
        digitsEl.textContent = [filled, empty].filter(Boolean).join(' ');
    }

    function showStatus(msg) {
        statusEl.textContent = msg;
    }

    function showDomainStatus(msg) {
        document.getElementById("domain-status").textContent = msg;
    }

    function formatError(err) {
        if (err === null || err === undefined) return String(err);
        if (typeof err === 'string') return err;
        if (typeof err === 'object') {
            if (typeof err.error === 'string') return err.error;
            if (typeof err.message === 'string') return err.message;
            if (err.conference) return String(err.conference);
            try { return JSON.stringify(err); } catch (e) { return String(err); }
        }
        return String(err);
    }

    function playPromptAudio(type, lang) {
        if (!config.ivr_tts) return;

        if (currentAudio) {
            currentAudio.pause();
            currentAudio.currentTime = 0;
        }
        currentAudio = new Audio(`./${type}_${lang}.mp3`);
        currentAudio.play();
        currentAudio.onended = () => {
            currentAudio = null;
        };
    }

    function showPrompt() {
        if (messageEl.innerHTML === prompts[lang][stage]) return;
        if (stage === "domain" && Object.keys(domains).length > 1) {
            messageEl.innerHTML = prompts[lang].domain;
            domainsEl.classList.remove("hidden");
            domainsEl.innerHTML = Object.values(domains)
                .map(d => {
                    const iconSrc = `./images/domain-icons/${encodeURIComponent(d.key)}.png`;
                    return `<div class="domain-item" style="display:flex;align-items:center;justify-content:space-between;padding:6px 8px;border-radius:6px;margin:6px 0;background:#fff;border:1px solid #e2e2e2;">
                                <div style="display:flex;align-items:center;gap:8px;min-width:0;">
                                  <div style="width:34px;height:34px;display:flex;align-items:center;justify-content:center;border:1px solid #ccc;border-radius:6px;font-weight:700;background:#fafafa;flex:0 0 34px;">${d.id}</div>
                                  <div style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0;flex:1;">${d.name}</div>
                                </div>
                                <img src="${iconSrc}" alt="" style="width:28px;height:28px;object-fit:contain;margin-left:12px;flex:0 0 28px;" onerror="this.style.display='none'">
                            </div>`;
                })
                .join("");
            playPromptAudio("platform", lang);
        } else {
            messageEl.innerHTML = prompts[lang].room;
            domainsEl.innerHTML = '';
            domainsEl.classList.add("hidden");
            playPromptAudio("conference", lang);
        }
    }

    let firstDigitEntered = false;

    function activateDigitsHalo() {
        if (!firstDigitEntered) {
            digitsEl.classList.add("active");
            firstDigitEntered = true;
        }
    }

    function handleInput(char) {
        activateDigitsHalo()
        if (/^[a-zA-Z0-9-_/]$/.test(char)) {
            if (stage === "domain") inputDigits = [char];
            else inputDigits.push(char);
        } else if (char === '*') {
            inputDigits.pop();
        } else if (char === '#') {
            if (stage === "domain") {
                const domainId = parseInt(inputDigits.join(''), 10);
                if (!isNaN(domainId) && domains[domainId]) {
                    selectedDomain = domains[domainId];
                    showDomainStatus(messages[lang].chosenDomain(domainId, selectedDomain.name));
                    document.getElementById("domain-status").style.display = "block";
                    window.browsing = selectedDomain.key;
                    inputDigits = [];
                    stage = "room";
                    updateDisplay();
                    if (stage === "room") digitsEl.classList.add("room-mode");
                    if (pendingRoomId) {
                        digitsEl.style.visibility = "hidden";
                        (pendingRoomId + '#').split('').forEach(handleInput);
                        pendingRoomId = null;
                    } else {
                        showPrompt();
                    }
                } else {
                    showStatus(messages[lang].invalid(inputDigits.join('')));
                }
            } else if (stage === "room") {
                // If we are waiting for user confirmation to proceed despite mapping failure
                if (waitingConfirm && inputDigits.join('') === (waitingConfirm.roomId || '')) {
                    // call proceed() to resolve the room.getConferenceName() promise
                    try {
                        waitingConfirm.proceed();
                    } catch (e) {
                        console.error("Failed to proceed despite mapping error", e);
                    }
                    waitingConfirm = null;
                    // keep UI; the initRoom's success callback will handle hiding UI
                    return;
                }
                const roomId = inputDigits.join('');
                if (expectedLength === 0 || inputDigits.length >= expectedLength) {
                    const room = new Room({ ...config, webrtc_domain: selectedDomain.domain });
                    room.initRoom(
                        roomId,
                        () => {
                            console.log("Room retrieved successfully:", room.roomName);
                            window.room = room;
                            digitsEl.style.display = "none";
                            messageEl.style.display = "none";
                            statusEl.style.display = "none";
                            domainsEl.style.display = "none";
                            document.removeEventListener('keydown', keyEvent);
                        },
                        (errorReason) => {
                            // If the room mapping failed but the room.js provided a proceed() callback,
                            // store it and ask the user to press '#' to continue anyway.
                            if (errorReason && typeof errorReason.proceed === 'function') {
                                waitingConfirm = { proceed: errorReason.proceed, roomId };
                                console.error("Mapping failed; waiting user confirmation:", errorReason.error);
                                const errMsg = formatError(errorReason.error);
                                showStatus(messages[lang].invalid(errMsg) + " " + messages[lang].confirmContinue);
                                digitsEl.style.visibility = "visible";
                                // do not call showPrompt() to keep the state waiting for '#'
                            } else {
                                console.error("Error entering room:", errorReason.error);
                                const errMsg = formatError(errorReason && errorReason.error ? errorReason.error : errorReason);
                                showStatus(messages[lang].invalid(errMsg));
                                digitsEl.style.visibility = "visible";
                                showPrompt();
                            }
                        }
                    );
                } else {
                    showStatus(messages[lang].incomplete(inputDigits.length, expectedLength));
                    digitsEl.style.visibility = "visible";
                    showPrompt();
                }
            }
            return;
        }
        updateDisplay();
        showStatus("");
    }

    function keyEvent(e) {
        handleInput(e.key);
    }
    document.addEventListener('keydown', keyEvent);

    // Auto-enter from URL
    const urlParams = new URLSearchParams(window.location.search);
    const urlDomainId = urlParams.get("domainId");
    const urlDomainKey = urlParams.get("domainKey");
    const urlRoomId = urlParams.get("roomId");
    const urlMixedId = urlParams.get("mixedId");

    if (urlRoomId && urlRoomId !== '0') pendingRoomId = urlRoomId;

    if (urlMixedId) {
        let d = null, r = null;
        if (/^[1-9]$/.test(urlMixedId)) {
            d = urlMixedId;
        } else {
            // Split on '#' or '.'
            const parts = urlMixedId.split(/[#.]/);
            if (parts.length === 2) {
                [d, r] = parts;
            } else {
                r = urlMixedId;
            }
        }
        if (r && !/^[0-9]$/.test(r)) pendingRoomId = r;
        if (d && /^[1-9]$/.test(d)) {
            if (domains[d]) {
                selectedDomain = domains[d];
                (selectedDomain.id + '#').split('').forEach(handleInput);
                console.log(`Auto-selected domain (from mixedId): ${selectedDomain.name}`);
                showDomainStatus(messages[lang].chosenDomain(d, selectedDomain.name));
            }
        }
    }

    if (urlDomainKey) {
        const found = Object.values(domains).find(d => d.key === urlDomainKey);
        if (found) {
            selectedDomain = found;
            (selectedDomain.id + '#').split('').forEach(handleInput);
            showDomainStatus(messages[lang].chosenDomain(found.id, found.name));
        }
    } else if (urlDomainId && domains[urlDomainId]) {
        selectedDomain = domains[urlDomainId];
        (selectedDomain.id + '#').split('').forEach(handleInput);
        console.log(`Auto-selected domain (by id): ${selectedDomain.name}`);
        showDomainStatus(messages[lang].chosenDomain(urlDomainId, selectedDomain.name));
    }

    if (!selectedDomain && Object.keys(domains).length === 1) {
        selectedDomain = Object.values(domains)[0];
        (selectedDomain.id + '#').split('').forEach(handleInput);
        console.log(`Single domain mode: auto-selected ${selectedDomain.name}`);
    }

    if (!selectedDomain) {
        showPrompt();
        updateDisplay();
    }
}

window.showQrCode = function(qrB64, pairingCode, pairingUrl) {
    let old = document.getElementById('qr-container');
    if (old) old.remove();

    let container = document.createElement('div');
    container.id = 'qr-container';

    // QR
    let qrDiv = document.createElement('div');
    qrDiv.id = 'qr-overlay';

    let img = document.createElement('img');
    img.src = 'data:image/png;base64,' + qrB64;
    qrDiv.appendChild(img);
    container.appendChild(qrDiv);

    if (pairingCode && pairingUrl) {
        // Pairing
        let info = document.createElement('div');
        info.id = 'pairing-info';
        info.innerHTML = `Code: ${pairingCode} <br/> (<a href="${pairingUrl}" target="_blank">${pairingUrl}</a>)`;
        container.appendChild(info);
    }
    document.body.appendChild(container);
};

window.updateQrCode = function(qrB64, pairingCode, pairingUrl) {
    // Ensure qr-container exists
    let container = document.getElementById('qr-container');
    if (!container) {
        container = document.createElement('div');
        container.id = 'qr-container';
        document.body.appendChild(container);
    }

    // Ensure qr-overlay exists
    let qrDiv = document.getElementById('qr-overlay');
    if (!qrDiv) {
        qrDiv = document.createElement('div');
        qrDiv.id = 'qr-overlay';
        container.appendChild(qrDiv);
    }

    // Ensure img exists
    let img = qrDiv.querySelector('img');
    if (!img) {
        img = document.createElement('img');
        qrDiv.appendChild(img);
    }
    img.src = 'data:image/png;base64,' + qrB64;

    // Update or create pairing-info
    let info = document.getElementById('pairing-info');
    if (!info && pairingCode && pairingUrl) {
        info = document.createElement('div');
        info.id = 'pairing-info';
        container.appendChild(info);
    }
    if (info) {
        info.innerHTML = `Code: ${pairingCode} <br/> (<a href="${pairingUrl}" target="_blank">${pairingUrl}</a>)`;
    }
};