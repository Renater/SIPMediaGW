import { Room } from './room.js';

const prompts = {
    fr: {
        domain: "Veuillez entrer le numéro de la plateforme suivi de #<br>(utilisez * pour corriger)",
        room: "Veuillez entrer le numéro de votre conférence suivi de #<br>(utilisez * pour corriger)"
    },
    en: {
        domain: "Please enter the platform number followed by #<br>(use * to correct)",
        room: "Please enter your conference number followed by #<br>(use * to correct)"
    }
};

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

    const lang = config['lang'] || 'fr';
    const expectedLength = parseInt(config['min_ivr_digit_length'], 10) || 0;
    const domains = parseDomains(config['webrtc_domains']);

    let inputDigits = [];
    let stage = "domain"; // 'domain' -> 'room'
    let selectedDomain = null;
    let pendingRoomId = null;

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

    function playPromptAudio(type, lang) {
        if (!config.ivr_tts) return;
        const audio = new Audio(`./${type}_${lang}.mp3`);
        audio.play();
    }

    function showPrompt() {
        if (messageEl.innerHTML === prompts[lang][stage]) return;
        if (stage === "domain" && Object.keys(domains).length > 1) {
            messageEl.innerHTML = prompts[lang].domain;
            domainsEl.classList.remove("hidden");
            domainsEl.innerHTML = Object.values(domains)
                .map(d => `<div class="domain-item"><span class="domain-id">${d.id}:</span> ${d.name}</div>`)
                .join("");
            playPromptAudio("platform", lang);
        } else {
            messageEl.innerHTML = prompts[lang].room;
            domainsEl.innerHTML = '';
            domainsEl.classList.add("hidden");
            playPromptAudio("conference", lang);
        }
    }

    function handleInput(char) {
        if (/^[a-zA-Z0-9-]$/.test(char)) {
            if (stage === "domain") inputDigits = [char];
            else inputDigits.push(char);
        } else if (char === '*') {
            inputDigits.pop();
        } else if (char === '#') {
            if (stage === "domain") {
                const domainId = parseInt(inputDigits.join(''), 10);
                if (!isNaN(domainId) && domains[domainId]) {
                    selectedDomain = domains[domainId];
                    showStatus(messages[lang].chosenDomain(domainId, selectedDomain.name));
                    window.browsing = selectedDomain.key;
                    inputDigits = [];
                    stage = "room";
                    updateDisplay();
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

    if (urlRoomId && urlRoomId !== '0') pendingRoomId = urlRoomId;

    if (urlDomainKey) {
        const found = Object.values(domains).find(d => d.key === urlDomainKey);
        if (found) {
            selectedDomain = found;
            (selectedDomain.id + '#').split('').forEach(handleInput);
            showStatus(messages[lang].chosenDomain(found.id, found.name));
            updateDisplay();
        }
    } else if (urlDomainId && domains[urlDomainId]) {
        selectedDomain = domains[urlDomainId];
        (selectedDomain.id + '#').split('').forEach(handleInput);
        console.log(`Auto-selected domain (by id): ${selectedDomain.name}`);
        showStatus(messages[lang].chosenDomain(urlDomainId, selectedDomain.name));
        updateDisplay();
    }

    if (!selectedDomain && Object.keys(domains).length === 1) {
        selectedDomain = Object.values(domains)[0];
        (selectedDomain.id + '#').split('').forEach(handleInput);
        console.log(`Single domain mode: auto-selected ${selectedDomain.name}`);
        updateDisplay();
    }

    if (!selectedDomain) {
        showPrompt();
        updateDisplay();
    }
}