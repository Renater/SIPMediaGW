import { Room } from './room.js';

const prompts = {
    fr: "Veuillez entrer le numéro de votre conférence suivi de #<br>(utilisez * pour corriger)",
    en: "Please enter your conference number followed by #<br>(use * to correct)"
};

const messages = {
    fr: {
        valid: code => `Code validé : ${code}`,
        invalid: error => `Le code de la réunion n'est pas valide ('${error}')`,
        incomplete: (count, expected) => `L'identifiant de la réunion est trop court (${count}/${expected})`,
        error: reason => `Erreur : ${reason}`
    },
    en: {
        valid: code => `Code validated: ${code}`,
        invalid: error => `The meeting room ID is not valide ('${error}')`,
        incomplete: (count, expected) => `The meeting room ID is too short (${count}/${expected})`,
        error: reason => `Error: ${reason}`
    }
};

document.getElementById("digits").addEventListener("beforeinput", e => {
    e.preventDefault();
});

// Load config and initialize IVR
fetch("../config.json")
    .then(res => res.json())
    .then(config => initIVR(config))
    .catch(err => console.error("Failed to load config.json", err));

function initIVR(config) {
    const messageEl = document.getElementById("message");
    const digitsEl = document.getElementById("digits");
    const statusEl = document.getElementById("status");

    const lang = config['lang'] || 'fr';
    const expectedLength = parseInt(config['min_ivr_digit_length'], 10) || 0;

    const room = new Room(config);
    let inputDigits = [];

    function updateDisplay() {
        const filled = inputDigits.join(' ');
        const empty = Array(Math.max(0, expectedLength - inputDigits.length)).fill('_').join(' ');
        digitsEl.textContent = [filled, empty].filter(Boolean).join(' ');
    }

    function showStatus(msg) {
        statusEl.textContent = msg;
    }

    function showPrompt(lang) {
        messageEl.innerHTML = prompts[lang] || prompts.en;
    }

    function handleInput(char) {
        if (/^[a-zA-Z0-9-]$/.test(char)) {
            inputDigits.push(char);
        } else if (char === '*') {
            inputDigits.pop();
        } else if (char === '#') {
            const roomId = inputDigits.join('');
            if (expectedLength==0 || inputDigits.length >= expectedLength) {
                //showStatus(messages[lang].valid(roomId));
                room.initRoom(
                    roomId,
                    () => {
                        console.log("Room retrieved successfully:", room.roomName);
                        window.room = room;
                        digitsEl.style.display = "none";
                        messageEl.style.display = "none";
                        statusEl.style.display = "none";
                        document.removeEventListener('keydown', keyEvent);
                    },
                    (errorReason) => {
                        console.error("Error entering room:", errorReason.error);
                        showStatus(messages[lang].invalid(errorReason.error));
                        digitsEl.style.visibility = "visible";
                        showPrompt(lang);
                    }
                );
            } else {
                showStatus(messages[lang].incomplete(inputDigits.length, expectedLength));
                digitsEl.style.visibility = "visible";
                showPrompt(lang);
            }
            return;
        }
        updateDisplay();
        showStatus("");
    }

    function keyEvent(e){
        const key = e.key;
            handleInput(key);
    };
    document.addEventListener('keydown', keyEvent);

    // Room ID provided in URL
    const urlRoomId = new URLSearchParams(window.location.search).get("roomId");
    if (urlRoomId && urlRoomId != '0') {
        console.log(`Auto-entering room: ${urlRoomId}`);
        digitsEl.style.visibility = "hidden";
        (urlRoomId+'#').split('').forEach(handleInput);
        //digitsEl.style.visibility = "hidden";
        return; // Skip prompt
    }
    // Initial display
    showPrompt(lang);
    updateDisplay();
}
