import { Room } from './room.js';

const messages = {
    fr: {
        valid: code => `Code validé : ${code}`,
        invalid: error => `Le code n'est pas valide ('${error}')`,
        incomplete: (count, expected) => `Le code est trop court (${count}/${expected})`,
        error: reason => `Erreur : ${reason}`,
        chosenDomain: (id, name) => `Plateforme sélectionnée (${id}) : ${name}`
    },
    en: {
        valid: code => `Code validated: ${code}`,
        invalid: error => `The code is not valid ('${error}')`,
        incomplete: (count, expected) => `The code is too short (${count}/${expected})`,
        error: reason => `Error: ${reason}`,
        chosenDomain: (id, name) => `Platform selected (${id}): ${name}`
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
                .map(d => `<div class="domain-item"><span class="domain-id">${d.id}</span> ${d.name}</div>`)
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
                            console.error("Error entering room:", errorReason.error);
                            showStatus(messages[lang].invalid(errorReason.error));
                            digitsEl.style.visibility = "visible";
                            showPrompt();
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