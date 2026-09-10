const urlParams = new URLSearchParams(window.location.search);
const gwId = urlParams.get('gwId');

let pollingStarted = false;
let ivrMenus = {};
let webrtcDomains = {};
let roomNameInfo = {};
let browsingName = '';
let menuOptions = [];
let menuDisplayed = false;
const POLL_MS = 2000;
// Signature of the screen implied by the gateway state. Redrawing on every
// poll would clear a half-typed conference id and reset the scroll position,
// so the page only rebuilds when this value changes.
let lastScreen = null;
let currentLang = 'en';

// ---------------------------------------------------------------------------
// Per-deployment settings, gathered here rather than spread through the markup.
// The pairing page carries the same block.
// ---------------------------------------------------------------------------
const BRAND = {
  name: 'SIPMediaGW',
  tagline: '',
  logo: '',                       // empty hides it
};

const TEXTS = {
  fr: {
    title: 'Contrôler votre réunion',
    pickPlatform: 'Choisissez la plateforme de votre réunion',
    roomName: 'Nom de la salle :',
    roomUri: 'Adresse vidéo :',
    connecting: 'connexion en cours…',
    waiting: 'En attente de la connexion d\u2019un terminal de visioconf\u00e9rence.',
    meetingLabel: 'Veuillez saisir l\u2019identifiant de la r\u00e9union',
    meetingFallback: 'Entrez le nom de la réunion',
    join: 'Rejoindre',
    hangUp: 'Raccrocher',
    confirmTitle: 'Confirmation',
    confirmBody: 'Êtes-vous sûr de vouloir terminer l\u2019appel ?',
    confirmNo: 'Annuler',
    confirmYes: 'Raccrocher',
    close: 'Fermer',
    hangUpTitle: 'Mettre fin \u00e0 l\u2019appel',
    themeToLight: 'Passer en thème clair',
    themeToDark: 'Passer en thème sombre',
  },
  en: {
    title: 'Control your meeting',
    pickPlatform: 'Choose your meeting platform',
    roomName: 'Room name:',
    roomUri: 'Video address:',
    connecting: 'connecting…',
    waiting: 'Waiting for a room endpoint to call in.',
    meetingLabel: 'Please enter the meeting id',
    meetingFallback: 'Enter the meeting name',
    join: 'Join',
    hangUp: 'Hang up',
    confirmTitle: 'Confirmation',
    confirmBody: 'Are you sure you want to end the call?',
    confirmNo: 'Cancel',
    confirmYes: 'Hang up',
    close: 'Close',
    hangUpTitle: 'End the call',
    themeToLight: 'Switch to light theme',
    themeToDark: 'Switch to dark theme',
  },
};

let dark = localStorage.getItem('theme')
  ? localStorage.getItem('theme') === 'dark'
  : window.matchMedia('(prefers-color-scheme: dark)').matches;

const $ = (id) => document.getElementById(id);

// defined early so the startup callback below can call it
function updateSlideControlsVisibility() {
  const ctrl = document.getElementById('slide-controls');
  if (!ctrl) return;
  // Only in the meeting: the two connection screens have nothing to capture.
  ctrl.style.display = menuDisplayed ? 'flex' : 'none';
}

function getRoomNamePlaceholder() {
  const captureEl = document.getElementById('key-capture');
  if (!captureEl) return '';
  const selectedInfo = browsingName && roomNameInfo[browsingName] ? roomNameInfo[browsingName] : null;
  const lang = currentLang === 'fr' ? 'fr' : 'en';
  const fallback = TEXTS[lang].meetingFallback;
  return selectedInfo?.placeholder?.[lang] || selectedInfo?.placeholder?.en || fallback;
}

function updateRoomNameInputUi() {
  const captureEl = document.getElementById('key-capture');
  const hintEl = document.getElementById('room-name-hint');
  if (!captureEl) return;

  const selectedInfo = browsingName && roomNameInfo[browsingName] ? roomNameInfo[browsingName] : null;
  const lang = currentLang === 'fr' ? 'fr' : 'en';
  const placeholder = getRoomNamePlaceholder();
  const hint = selectedInfo?.hint?.[lang] || selectedInfo?.hint?.en || '';

  const labelEl = document.getElementById('meeting-label');
  if (labelEl) labelEl.textContent = TEXTS[currentLang].meetingLabel;

  captureEl.placeholder = captureEl.value ? '' : placeholder;
  if (hintEl) {
    hintEl.textContent = hint;
    hintEl.style.display = hint ? 'block' : 'none';
  }
}

// Redraws everything the language or the theme changes. The two connection
// screens are plain text; the in-meeting keys are relabelled where they exist.
function renderLangSwitch() {
  const t = TEXTS[currentLang];

  document.documentElement.lang = currentLang;
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';

  $('lang-fr').setAttribute('aria-checked', String(currentLang === 'fr'));
  $('lang-en').setAttribute('aria-checked', String(currentLang === 'en'));

  const toggle = $('theme-toggle');
  toggle.textContent = dark ? '\u2600' : '\u263e';
  toggle.setAttribute('aria-pressed', String(dark));
  toggle.setAttribute('aria-label', dark ? t.themeToLight : t.themeToDark);

  $('brand-name').textContent = BRAND.name;
  $('brand-tagline').textContent = BRAND.tagline;
  if (BRAND.logo) { $('brand-logo').src = BRAND.logo; $('brand-logo').alt = BRAND.name; }

  $('title-text').textContent = t.title;
  $('platforms-subtitle').textContent = t.pickPlatform;
  $('waiting').textContent = t.waiting;
  $('room-name-label').textContent = t.roomName;
  $('room-uri-label').textContent = t.roomUri;
  $('btn-enter-label').textContent = t.join;

  const endBtn = $('btn-endcall');
  if (endBtn) {
    endBtn.textContent = t.hangUp;
    endBtn.title = t.hangUpTitle;
  }
  $('confirm-title').textContent = t.confirmTitle;
  $('confirm-body').textContent = t.confirmBody;
  $('confirm-no').textContent = t.confirmNo;
  $('confirm-yes').textContent = t.confirmYes;
  $('confirm-close').setAttribute('aria-label', t.close);

  const ss = $('btn-slideShot');
  if (ss) ss.textContent = 'Capture';

  updateRoomNameInputUi();
  showRoom();
}

// Which of the two connection screens is up, or neither once in the meeting.
function showScreen(name) {
  $('screen-platforms').hidden = (name !== 'platforms');
  $('screen-meeting').hidden = (name !== 'meeting');
  $('btn-endcall').hidden = false;
  $('title').hidden = (name === null);
  $('room').hidden = (name === null);

  // Command feedback and the request log belong to the meeting: on the way in
  // they would only show the keys the page sends on the visitor's behalf.
  const inMeeting = (name === null);
  $('status').hidden = !inMeeting;
  $('log').hidden = !inMeeting;
  // Hanging up stays available throughout: reaching the wrong room is exactly
  // the sort of mistake to correct before joining anything.
}

// The room this page drives. Both values come from the same status poll that
// drives the screens, and read as pending until the call is up.
let roomName = '';
let roomUri = '';

// Set once a hang-up has been asked for. The status poll clears room and
// browsing before gw_state turns to stopped, so without this the page would
// drop back to the platform list for a poll or two on its way out.
let leaving = false;

function showRoom() {
  const t = TEXTS[currentLang];
  const known = !!(roomName || roomUri);
  $('room').classList.toggle('room--pending', !known);
  $('room-name').textContent = roomName || t.connecting;
  $('room-uri').textContent = roomUri || t.connecting;

  // Until an endpoint has called in there is nothing on the other end: a
  // platform key would go nowhere, and there is no call to hang up. The
  // screen stays readable, it just does not act yet.
  $('platforms').classList.toggle('is-waiting', !known);
  $('platforms').querySelectorAll('button').forEach((b) => { b.disabled = !known; });
  $('btn-endcall').disabled = !known;
  $('waiting').hidden = known;
}

const capture = document.getElementById('key-capture');
updateRoomNameInputUi();

function captureReset() {
  capture.value = '';
  updateRoomNameInputUi();
}


capture.addEventListener('input', function() {
  this.placeholder = this.value ? '' : getRoomNamePlaceholder();
});
capture.addEventListener('keydown', async function(e) {
  if (e.key === 'Enter') {
    e.preventDefault();
    if (this.value.length > 0) {
      //await sendString(this.value + '#');
      await sendRoomName(this.value);
      await captureReset();
      await setTimeout(() => sendKey('#'), 450);
    }
  }
});

function apiUrl(path) {
  const url = `${window.location.protocol}//${window.location.hostname}${window.location.port ? ':' + window.location.port : ''}`;
  return `${url.replace(/\/$/, '')}${path}`;
}

async function sendEndCall() {
  const status = document.getElementById('status');
  const log = document.getElementById('log');
  const payload = { gw_id: gwId, payload: { command: "endCall" } };
  status.textContent = currentLang === 'fr' ? "Envoi: fin d'appel…" : "Sending: end call…";
  log.textContent = `→ POST ${apiUrl('/command')}\n   ${JSON.stringify(payload)}`;
  try {
    const res = await fetch(apiUrl('/command'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const text = await res.text();
    status.textContent = `✓ ${res.status} — end call`;
    log.textContent += `\n← ${res.status} ${text.slice(0, 120)}`;
    // after requesting hangup, keep polling to observe end state
    if (!pollingStarted) { pollingStarted = true; setTimeout(checkGwStatus, 1000); }
  } catch (e) {
    status.textContent = `✗ End call error: ${e.message}`;
    log.textContent += `\n← ${e.message}`;
  }
}

// One request shape, four commands. They differ only in what they send and
// what they say afterwards, so the differences are arguments: the command
// name, the label shown on success, and whether the reply should start the
// status poll — sendKey and roomName only arm it on a submit key, since the
// gateway has nothing new to report until the entry is confirmed.
async function sendCommand(command, param1, { successLabel, startPolling }) {
  const status = document.getElementById('status');
  const log = document.getElementById('log');
  const payload = { gw_id: gwId, payload: { command, param1 } };
  status.textContent = `Sending: ${param1}`;
  log.textContent = `→ POST ${apiUrl('/command')}\n   ${JSON.stringify(payload)}`;
  try {
    const res = await fetch(apiUrl('/command'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const text = await res.text();
    status.textContent = `✓ ${res.status} — ${successLabel}`;
    log.textContent += `\n← ${res.status} ${text.slice(0, 120)}`;
    if (startPolling && !pollingStarted) { pollingStarted = true; setTimeout(checkGwStatus, 1000); }
  } catch (e) {
    status.textContent = `✗ Error: ${e.message}`;
    log.textContent += `\n← ${e.message}`;
  }
}

// A submit key confirms an entry: only then is there something new to poll for.
const isSubmitKey = k => k === '#' || k === 'Enter';

async function sendKey(param1) {
  return sendCommand('sendKey', param1, {
    successLabel: `key: ${param1}`,
    startPolling: isSubmitKey(param1),
  });
}

async function sendString(str) {
  return sendCommand('sendString', str, {
    successLabel: `string: ${str}`,
    startPolling: true,
  });
}

async function sendRoomName(param1) {
  return sendCommand('roomName', param1, {
    successLabel: `room name: ${param1}`,
    startPolling: isSubmitKey(param1),
  });
}

async function sendChat(message) {
  return sendCommand('sendChat', message, {
    successLabel: 'chat sent',
    startPolling: true,
  });
}


async function fetchIvrConfigAndRestoreState() {
  if (!gwId) return;
  try {
    const res = await fetch(apiUrl('/ivrConfig') + `?gw_id=${encodeURIComponent(gwId)}`);
    const data = await res.json();
    ivrMenus = data.menus || {};
    webrtcDomains = data.webrtc_domains || {};
    roomNameInfo = data.room_name_info || {};
    renderLangSwitch();
    const statusRes = await fetch(apiUrl('/status') + `?gw_id=${encodeURIComponent(gwId)}`);
    if (!statusRes.ok) { renderDomainButtons(); return; }
    const statusData = await statusRes.json();
    let bn = statusData.data.browsing;
    let rn = statusData.data.room;
    lastScreen = `${bn || ''}|${rn || ''}`;
    if (rn && bn) {
      menuOptions = (ivrMenus[bn] && ivrMenus[bn].options) ? ivrMenus[bn].options : [];
      menuDisplayed = true;
      renderMenuOptions();
    } else {
      bn ? showInputAndPrepareMenu(bn) : renderDomainButtons();
    }
  } catch(e) {
    document.getElementById('status').textContent = "Error loading IVR config.";
  }
}

function renderDomainButtons() {
  const list = $('platforms');
  const domains = Object.entries(webrtcDomains);
  if (!domains.length) return;

  menuDisplayed = false;
  updateSlideControlsVisibility();
  showScreen('platforms');

  list.innerHTML = '';
  domains.forEach(([key, val], idx) => {
    // Still the key the gateway expects, even though the card no longer shows
    // it: a finger on the card replaces a digit on the keypad.
    const digit = String(idx + 1);

    // The name may carry its host in parentheses when no domain field is set.
    const rawName = val.name || key;
    const name = rawName.replace(/\s*\(.*\)$/, '').trim();
    const host = val.domain || (rawName.match(/\(([^)]+)\)\s*$/) || [])[1] || '';

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'platform';
    btn.setAttribute('aria-label', name);

    const icon = document.createElement('img');
    icon.className = 'platform__icon';
    icon.alt = '';
    icon.src = `${apiUrl('/logo')}/${encodeURIComponent(key)}?gw_id=${encodeURIComponent(gwId)}`;
    // A connector with no logo shipped simply shows none: the previous fallback
    // pointed at a relative path that stopped resolving once the page moved to
    // the proxy, so it only ever produced a second 404.
    icon.addEventListener('error', () => { icon.remove(); });

    const text = document.createElement('span');
    text.className = 'platform__text';
    const nameEl = document.createElement('span');
    nameEl.className = 'platform__name';
    nameEl.textContent = name;
    text.appendChild(nameEl);
    if (host) {
      const hostEl = document.createElement('span');
      hostEl.className = 'platform__host';
      hostEl.textContent = host;
      text.appendChild(hostEl);
    }

    btn.append(icon, text);
    btn.onclick = async () => {
      await sendKey(digit);
      await sendKey('#');
      showInputAndPrepareMenu(key);
    };
    list.appendChild(btn);
  });

  showRoom();     // a card built now takes the current waiting state
}

function showInputAndPrepareMenu(selectedDomainKey) {
  browsingName = selectedDomainKey;
  menuOptions = [];
  menuDisplayed = false;
  renderMenuOptions();
  showScreen('meeting');

  // The platform is recalled at the top: there is no way back to the list, the
  // gateway cannot return to its menu once a platform has been chosen.
  const val = webrtcDomains[selectedDomainKey] || {};
  const name = (val.name || selectedDomainKey).replace(/\s*\(.*\)$/, '').trim();
  $('chosen-name').textContent = name;
  const icon = $('chosen-icon');
  icon.src = `${apiUrl('/logo')}/${encodeURIComponent(selectedDomainKey)}?gw_id=${encodeURIComponent(gwId)}`;
  icon.alt = '';
  icon.hidden = false;
  icon.onerror = () => { icon.hidden = true; };

  const capture = $('key-capture');
  capture.disabled = false;
  updateRoomNameInputUi();
  refreshJoin();

  if (!document.activeElement || document.activeElement === document.body) {
    capture.focus();
  }

  updateSlideControlsVisibility();
}

// Nothing to send until something is typed.
function refreshJoin() {
  const capture = $('key-capture');
  $('btn-enter').disabled = !capture || !capture.value.trim();
}

async function checkGwStatus() {
  if (!gwId) return setTimeout(checkGwStatus, POLL_MS);
  try {
    const statusRes = await fetch(apiUrl('/status') + `?gw_id=${encodeURIComponent(gwId)}`);
    // A transient failure must not silence the page for good: it keeps
    // polling, more slowly, so a passing outage is recovered from.
    if (!statusRes.ok) { document.getElementById('status').textContent = `Gateway unreachable (code ${statusRes.status}) — retrying…`; return setTimeout(checkGwStatus, POLL_MS * 5); }
    const statusData = await statusRes.json();
    // stopped: the container exited, the call is over. deleted: the VM is gone.
    // Either way there is nothing left to drive from here. The page used to
    // watch for "down", a value the proxy stopped writing when the states were
    // renamed.
    const state = statusData.data?.gw_state;
    if (state === "stopped" || state === "deleted") {
      $('status').hidden = false;
      $('status').textContent = currentLang === 'fr'
        ? 'L\u2019appel est termin\u00e9.'
        : 'The call has ended.';
      // a beat so the message is seen, then back to the pairing page
      setTimeout(() => { window.location.href = apiUrl('/pairing'); }, 800);
      return;
    }
    // The room this page drives, shown in the header.
    const peerName = statusData.data.peer_name || '';
    const peerUri = statusData.data.peer_uri || '';
    if (peerName !== roomName || peerUri !== roomUri) {
      roomName = peerName;
      roomUri = peerUri;
      showRoom();
    }

    let bn = statusData.data.browsing;
    let rn = statusData.data.room;

    // The gateway is the source of truth: the platform and the conference id
    // can be entered on the endpoint keypad just as well as here, so the
    // screen follows the reported state instead of what this page last did.
    const screen = `${bn || ''}|${rn || ''}`;
    if (!leaving && screen !== lastScreen) {
      lastScreen = screen;
      if (rn && bn) {
        menuOptions = (ivrMenus[bn] && ivrMenus[bn].options) ? ivrMenus[bn].options : [];
        menuDisplayed = true;
        showScreen(null);
        renderMenuOptions();
      } else if (bn) {
        showInputAndPrepareMenu(bn);
      } else {
        menuOptions = [];
        menuDisplayed = false;
        renderDomainButtons();
      }
    }
  } catch(e) {
    document.getElementById('status').textContent = `Status error — retrying…`;
    return setTimeout(checkGwStatus, POLL_MS * 5);
  }
  // Polling used to stop for good once the menu was drawn. The page then sat
  // on a call that had already ended, and never saw a platform picked from
  // the room keypad.
  setTimeout(checkGwStatus, POLL_MS);
}

function renderMenuOptions() {
  const menuDiv = document.getElementById('menu-options');
  menuDiv.innerHTML = '';
  if (!menuOptions.length) return;

  let chatInjected = false;

  // in the meeting: neither connection screen belongs on screen any more
  showScreen(null);

  // mark that we're showing the IVR/menu options inside the meeting
  menuDisplayed = true;

  // render existing options and inject chat input directly after the chat option (no toggle)
  for (const opt of menuOptions) {
    const btn = document.createElement('button');
    btn.className = 'key menu-key';
    btn.innerHTML = `${getIcon(opt.icon)} ${opt[currentLang] || opt['en'] || ''}`;
    btn.onclick = () => sendKey(opt.dtmf);
    menuDiv.appendChild(btn);

    // if this option represents chat (icon name contains 'chat'), append visible chat row right away
    if (!chatInjected && opt.icon && String(opt.icon).toLowerCase().includes('chat')) {
      chatInjected = true;

      const chatRow = document.createElement('div');
      chatRow.className = 'chat-row';

      const chatInput = document.createElement('input');
      chatInput.type = 'text';
      chatInput.className = 'chat-input';
      chatInput.placeholder = currentLang === 'fr' ? 'Envoyer un message au chat…' : 'Send a message to chat…';

      chatInput.addEventListener('keydown', async (e) => {
        if (e.key === 'Enter') {
          e.preventDefault();
          const v = chatInput.value.trim();
          if (v.length) { await sendChat(v); chatInput.value = ''; }
        }
      });

      const sendBtn = document.createElement('button');
      sendBtn.className = 'chat-send-btn key';
      sendBtn.textContent = currentLang === 'fr' ? 'Envoyer' : 'Send';
      sendBtn.onclick = async () => {
        const v = chatInput.value.trim();
        if (v.length) { await sendChat(v); chatInput.value = ''; }
      };

      chatRow.appendChild(chatInput);
      chatRow.appendChild(sendBtn);
      menuDiv.appendChild(chatRow);

      // focus first chat input when chat injected
      setTimeout(() => chatInput.focus(), 50);
      // DO NOT break — allow remaining menu options to render under the chat row
    }
  }

  // ensure slide controls are visible now that menu options are rendered
  updateSlideControlsVisibility();
}

function getIcon(icon) {
  if (!icon) return '';
  return `<img src="${apiUrl('/icon')}/${icon}?gw_id=${encodeURIComponent(gwId)}" alt="" style="width:1.5em;height:1.5em;vertical-align:middle;">`;
}

// The script is injected at the end of the body, so the document is already
// parsed by the time it runs and DOMContentLoaded has been and gone. Waiting
// for an event that has already fired would leave the page inert, so the
// state is only checked here, and the callback run straight away if parsing
// is done.
function onReady(fn) {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', fn);
  } else {
    fn();
  }
}

// Language and theme, wired like the pairing page's.
function setLang(value) {
  currentLang = value;
  localStorage.setItem('lang', value);
  renderLangSwitch();
}

$('lang-fr').addEventListener('click', () => setLang('fr'));
$('lang-en').addEventListener('click', () => setLang('en'));
$('theme-toggle').addEventListener('click', () => {
  dark = !dark;
  localStorage.setItem('theme', dark ? 'dark' : 'light');
  renderLangSwitch();
});

onReady(() => {
  const saved = localStorage.getItem('lang');
  if (saved && TEXTS[saved]) currentLang = saved;
  renderLangSwitch();
  fetchIvrConfigAndRestoreState();
  // call after initial render to hide slide-controls when appropriate
  updateSlideControlsVisibility();
  // Polling used to start only once the user had pressed something, so a page
  // opened on an idle gateway never noticed the room joining a conference.
  if (!pollingStarted) { pollingStarted = true; setTimeout(checkGwStatus, POLL_MS); }
});
$('key-capture').addEventListener('input', refreshJoin);

$('btn-enter').onclick = async () => {
  if (capture.value.length > 0) {
    $('spinner').hidden = false;
    $('btn-enter').disabled = true;
    //await sendString(capture.value + '#');
    await sendRoomName(capture.value);
    await captureReset();
    await setTimeout(() => sendKey('#'), 450);
  }
};
// Leaving is asked for twice: the browser's own confirm() sat at the top of the
// window, out of the page and out of its styling.
function askToHangUp() {
  $('confirm').hidden = false;
  $('confirm-no').focus();
}

function closeConfirm() {
  $('confirm').hidden = true;
  $('btn-endcall').focus();
}

$('btn-endcall').onclick = askToHangUp;
$('confirm-no').onclick = closeConfirm;
$('confirm-close').onclick = closeConfirm;
$('confirm-backdrop').onclick = closeConfirm;
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !$('confirm').hidden) closeConfirm();
});

$('confirm-yes').onclick = async () => {
  $('confirm-yes').disabled = true;
  $('btn-endcall').disabled = true;
  leaving = true;
  await sendEndCall();
  setTimeout(() => { window.location.href = apiUrl('/pairing'); }, 250);
};
// slideShot button bindings
document.getElementById('btn-slideShot').onclick = async () => { await sendSlideShot(); };
document.getElementById('slide-close').onclick = () => { hideSlidePreview(); };

function showSlidePreview(b64) {
  const panel = document.getElementById('slide-preview');
  const img = document.getElementById('slide-img');
  const dl = document.getElementById('slide-download');
  if (!panel || !img || !dl) return;
  const dataUrl = `data:image/png;base64,${b64}`;
  img.src = dataUrl;
  dl.href = dataUrl;
  dl.download = `slide_${Date.now()}.png`;
  updateFullscreenButtonLabel();
  panel.style.display = 'flex';
  panel.setAttribute('aria-hidden', 'false');
  document.getElementById('slide-backdrop').style.display = 'block';
  document.getElementById('slide-backdrop').setAttribute('aria-hidden', 'false');
}

function hideSlidePreview() {
  const panel = document.getElementById('slide-preview');
  if (!panel) return;
  if (document.fullscreenElement) {
    document.exitFullscreen().catch(()=>{});
  }
   panel.style.display = 'none';
   panel.setAttribute('aria-hidden', 'true');
   document.getElementById('slide-img').src = '';
   document.getElementById('slide-backdrop').style.display = 'none';
   document.getElementById('slide-backdrop').setAttribute('aria-hidden', 'true');
}

// Append a thumbnail to the gallery and wire click -> preview
function addSlideThumbnail(b64) {
  const gallery = document.getElementById('slide-gallery');
  if (!gallery) return;
  const wrapper = document.createElement('div');
  wrapper.style.display = 'flex';
  wrapper.style.flexDirection = 'column';
  wrapper.style.alignItems = 'flex-start';

  const img = document.createElement('img');
  img.className = 'slide-thumb';
  img.src = `data:image/png;base64,${b64}`;
  img.alt = 'Slide thumbnail';
  img.onclick = () => showSlidePreview(b64);

  const meta = document.createElement('div');
  meta.className = 'slide-thumb-meta';
  const t = new Date().toLocaleTimeString();
  meta.textContent = t;

  wrapper.appendChild(img);
  wrapper.appendChild(meta);
  // insert newest first
  gallery.insertBefore(wrapper, gallery.firstChild);
}

async function sendSlideShot() {
   const status = document.getElementById('status');
   const log = document.getElementById('log');
   const btn = document.getElementById('btn-slideShot');
   const payload = { gw_id: gwId, payload: { command: "slideShot" } };
   if (btn) { btn.disabled = true; }
   status.textContent = currentLang === 'fr' ? 'Envoi: capture…' : 'Sending: capture…';
   log.textContent = `→ POST ${apiUrl('/command')}\n   ${JSON.stringify(payload)}`;
   try {
     const res = await fetch(apiUrl('/command'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
     const json = await res.json();
     if (!res.ok || !json.data || !json.data.slideImg) {
       throw new Error(json.error?.message || 'No image returned');
     }
     status.textContent = `✓ ${res.status} — slide captured`;
     log.textContent += `\n← ${res.status} (slide received)`;
    // add to gallery and show preview for the new capture
    addSlideThumbnail(json.data.slideImg);
    showSlidePreview(json.data.slideImg);
   } catch (e) {
     status.textContent = currentLang === 'fr' ? `✗ Erreur capture: ${e.message}` : `✗ Capture error: ${e.message}`;
     log.textContent += `\n← ${e.message}`;
   } finally {
     if (btn) { btn.disabled = false; }
   }
 }

// toggle fullscreen using Fullscreen API
function updateFullscreenButtonLabel() {
  const fsBtn = document.getElementById('slide-fullscreen');
  if (!fsBtn) return;
  const isFs = !!document.fullscreenElement;
  fsBtn.textContent = isFs
    ? (currentLang === 'fr' ? 'Quitter' : 'Exit')
    : (currentLang === 'fr' ? 'Agrandir' : 'Full screen');
}

async function toggleFullscreen() {
  const panel = document.getElementById('slide-preview');
  if (!panel) return;
  try {
    if (!document.fullscreenElement) {
      if (panel.requestFullscreen) await panel.requestFullscreen();
    } else {
      if (document.exitFullscreen) await document.exitFullscreen();
    }
  } catch (e) {
    // ignore fullscreen errors
  }
  updateFullscreenButtonLabel();
}

document.addEventListener('fullscreenchange', updateFullscreenButtonLabel);

// wire fullscreen button
document.getElementById('slide-fullscreen').onclick = () => { toggleFullscreen(); };

// wire discard button: remove matching thumbnail(s) from gallery then close preview
document.getElementById('slide-discard').onclick = () => {
  const img = document.getElementById('slide-img');
  if (!img || !img.src) return;
  const confirmMsg = currentLang === 'fr' ? "Supprimer cette vignette ?" : "Discard this slide?";
  if (!confirm(confirmMsg)) return;
  const gallery = document.getElementById('slide-gallery');
  if (gallery) {
    const thumbs = Array.from(gallery.querySelectorAll('img.slide-thumb'));
    thumbs.forEach(t => {
      // compare data URLs exactly (thumbnails are created from same base64)
      if (t.src === img.src) {
        const wrap = t.parentElement;
        if (wrap) wrap.remove();
      }
    });
  }
  hideSlidePreview();
};
