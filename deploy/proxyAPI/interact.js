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
    editName: 'Modifier le nom affich\u00e9 dans la conf\u00e9rence',
    save: 'Valider',
    cancel: 'Annuler',
    chatPlaceholder: 'Envoyer un message au chat\u2026',
    chatSend: 'Envoyer',
    capture: 'Capturer l\u2019\u00e9cran partag\u00e9',
    captureHint: 'Prend une image du contenu partag\u00e9 pendant la r\u00e9union.',
    captureNone: 'Aucun contenu partag\u00e9 \u00e0 capturer pour le moment.',
    captureFail: 'La capture a \u00e9chou\u00e9.',
    slideTitle: 'Capture de l\u2019\u00e9cran partag\u00e9',
    slideDownload: 'T\u00e9l\u00e9charger',
    slideFullscreen: 'Plein \u00e9cran',
    slideShrink: 'R\u00e9duire',
    slideDiscard: 'Supprimer',
    discardBody: 'Supprimer cette capture ?',
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
    editName: 'Change the name shown in the conference',
    save: 'Save',
    cancel: 'Cancel',
    chatPlaceholder: 'Send a message to chat\u2026',
    chatSend: 'Send',
    capture: 'Capture the shared screen',
    captureHint: 'Takes a still of the content being shared in the meeting.',
    captureNone: 'Nothing is being shared to capture right now.',
    captureFail: 'The capture failed.',
    slideTitle: 'Shared screen capture',
    slideDownload: 'Download',
    slideFullscreen: 'Full screen',
    slideShrink: 'Shrink',
    slideDiscard: 'Discard',
    discardBody: 'Discard this capture?',
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

const ICON_DOWNLOAD = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 16l-5-5h3V4h4v7h3l-5 5zM5 18h14v2H5z"/></svg>';
const ICON_EXPAND = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 4h7v2H6v5H4V4zm9 0h7v7h-2V6h-5V4zM4 13h2v5h5v2H4v-7zm14 0h2v7h-7v-2h5v-5z"/></svg>';
const ICON_SHRINK = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 4v5H4V7h3V4h2zm6 0h2v3h3v2h-5V4zM4 15h5v5H7v-3H4v-2zm11 0h5v2h-3v3h-2v-5z"/></svg>';
const ICON_TRASH = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 7h12l-1 13H7L6 7zm3-3h6l1 2H8l1-2z"/></svg>';


// Messages are worth reading once — a gateway out of reach, a call that has
// ended — and then they are in the way. They fade on their own rather than
// sitting under the controls for the rest of the session.
let sayTimer = null;
function say(text) {
  const el = $('status');
  el.textContent = text || '';
  clearTimeout(sayTimer);
  if (text) sayTimer = setTimeout(() => { el.textContent = ''; }, 6000);
}

// A tooltip is centred on its element, which puts it off the page when the
// element sits near an edge - and where it sits depends on the text beside it.
// The side is therefore chosen as the pointer arrives, not written into the
// markup.
document.addEventListener('mouseover', (e) => {
  const el = e.target.closest('[data-tip]');
  if (!el) return;
  const box = el.getBoundingClientRect();
  const half = 0.5 * Math.min(window.innerWidth, 320);   // a tooltip's worst case
  delete el.dataset.tipAlign;
  if (box.left + box.width / 2 < half) el.dataset.tipAlign = 'left';
  else if (window.innerWidth - box.right + box.width / 2 < half) el.dataset.tipAlign = 'right';
}, true);

// defined early so the startup callback below can call it
function updateSlideControlsVisibility() {
  const ctrl = $('slide-controls');
  if (!ctrl) return;
  // Only in the meeting: the two connection screens have nothing to capture.
  ctrl.style.display = menuDisplayed ? 'flex' : 'none';
}

function getRoomNamePlaceholder() {
  const captureEl = $('key-capture');
  if (!captureEl) return '';
  const selectedInfo = browsingName && roomNameInfo[browsingName] ? roomNameInfo[browsingName] : null;
  const lang = currentLang === 'fr' ? 'fr' : 'en';
  const fallback = TEXTS[lang].meetingFallback;
  return selectedInfo?.placeholder?.[lang] || selectedInfo?.placeholder?.en || fallback;
}

function updateRoomNameInputUi() {
  const captureEl = $('key-capture');
  const hintEl = $('room-name-hint');
  if (!captureEl) return;

  const selectedInfo = browsingName && roomNameInfo[browsingName] ? roomNameInfo[browsingName] : null;
  const lang = currentLang === 'fr' ? 'fr' : 'en';
  const placeholder = getRoomNamePlaceholder();
  const hint = selectedInfo?.hint?.[lang] || selectedInfo?.hint?.en || '';

  const labelEl = $('meeting-label');
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

  document.title = BRAND.name;
  $('brand-name').textContent = BRAND.name;
  $('brand-tagline').textContent = BRAND.tagline;
  if (BRAND.logo) { $('brand-logo').src = BRAND.logo; $('brand-logo').alt = BRAND.name; }

  $('title-text').textContent = t.title;
  $('platforms-subtitle').textContent = t.pickPlatform;
  $('waiting').textContent = t.waiting;
  $('name-edit').dataset.tip = t.editName;
  $('name-edit').setAttribute('aria-label', t.editName);
  $('name-save').textContent = t.save;
  $('name-cancel').textContent = t.cancel;
  $('room-name-label').textContent = t.roomName;
  $('room-uri-label').textContent = t.roomUri;
  $('btn-enter-label').textContent = t.join;

  const endBtn = $('btn-endcall');
  if (endBtn) {
    endBtn.textContent = t.hangUp;
    endBtn.dataset.tip = t.hangUpTitle;
  }
  $('confirm-title').textContent = t.confirmTitle;
  $('confirm-body').textContent = t.confirmBody;
  $('confirm-no').textContent = t.confirmNo;
  // Only while closed: with the dialog open the label is the question's own.
  if ($('confirm').hidden) $('confirm-yes').textContent = t.confirmYes;
  $('confirm-close').setAttribute('aria-label', t.close);

  // The button only does anything while content is being shared, which the
  // old one-word label gave no hint of.
  $('slide-title').textContent = t.slideTitle;
  // Icon and word: the icon catches the eye, the word settles what it means.
  $('slide-download').innerHTML = ICON_DOWNLOAD + '<span></span>';
  $('slide-download').lastChild.textContent = t.slideDownload;
  $('slide-discard').innerHTML = ICON_TRASH + '<span></span>';
  $('slide-discard').lastChild.textContent = t.slideDiscard;
  $('slide-close').setAttribute('aria-label', t.close);
  $('slide-close').dataset.tip = t.close;

  const ss = $('btn-slideShot');
  if (ss) ss.textContent = t.capture;
  const hint = $('slide-hint');
  if (hint) hint.textContent = t.captureHint;

  updateRoomNameInputUi();
  showRoom();

  // The command labels come from config.json and are set when drawn: without
  // this they would stay in whichever language the screen was built in.
  if (menuDisplayed) renderMenuOptions();
}

// Which of the two connection screens is up, or neither once in the meeting.
// Which of the three screens is up. The title, the room block, the hang-up
// button and the message line belong to the frame and stay put: which room is
// being driven, and the way out of it, matter on every screen.
function showScreen(name) {
  $('screen-platforms').hidden = (name !== 'platforms');
  $('screen-meeting').hidden = (name !== 'meeting');
  $('screen-controls').hidden = (name !== null);
}

// The room this page drives. Both values come from the same status poll that
// drives the screens, and read as pending until the call is up.
let roomName = '';
let roomUri = '';

// The name the conference shows. It starts out as the endpoint's own — which
// is why the two usually match — but it is a separate value, and the only one
// of the pair the room may change.
let displayName = null;

// Set once a hang-up has been asked for. The status poll clears room and
// browsing before gw_state turns to stopped, so without this the page would
// drop back to the platform list for a poll or two on its way out.
let leaving = false;

async function fetchDisplayName() {
  if (!gwId) return;
  try {
    const res = await fetch(apiUrl('/command'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ gw_id: gwId, payload: { command: 'displayName' } }),
    });
    if (!res.ok) return;
    const json = await res.json();
    displayName = json?.data?.displayName || json?.data?.displayname || '';
    showRoom();
  } catch (e) {
    // Left as null: the line then falls back to the endpoint's own name.
  }
}

async function sendDisplayName(name) {
  if (!gwId) return;
  await sendCommand('displayName', name, {
    startPolling: false,
  });
  displayName = name;
  showRoom();
}

function startEditName() {
  $('name-input').value = displayName || roomName || '';
  ['room-name', 'name-edit'].forEach((id) => { $(id).hidden = true; });
  ['name-input', 'name-save', 'name-cancel'].forEach((id) => { $(id).hidden = false; });
  $('name-input').focus();
  $('name-input').select();
}

function stopEditName() {
  ['name-input', 'name-save', 'name-cancel'].forEach((id) => { $(id).hidden = true; });
  $('room-name').hidden = false;
  $('name-edit').hidden = false;
}

function showRoom() {
  const t = TEXTS[currentLang];
  const known = !!(roomName || roomUri);
  $('room').classList.toggle('room--pending', !known);
  $('room-name').textContent = displayName || roomName || t.connecting;
  $('room-uri').textContent = roomUri || t.connecting;

  // Until an endpoint has called in there is nothing on the other end: a
  // platform key would go nowhere, and there is no call to hang up. The
  // screen stays readable, it just does not act yet.
  $('platforms').classList.toggle('is-waiting', !known);
  $('platforms').querySelectorAll('button').forEach((b) => { b.disabled = !known; });
  $('btn-endcall').disabled = !known;
  $('waiting').hidden = known;
  // Nothing to rename until an endpoint is on the line.
  if (!known) stopEditName();
  // Only before the conference is joined: displayName goes into the connector's
  // URL when the browser starts, so changing it afterwards would move nothing.
  // Reaching into the platform's own interface, the way the mic and chat
  // commands do, would take a route of its own in the connector.
  $('name-edit').hidden = !known || menuDisplayed || !$('name-input').hidden;

  showInCall(known);
}

// Which conference, on which platform. Drawn from here rather than with the
// commands: the commands are redrawn only when the screen changes, while this
// has to follow the poll — platform, room and endpoint arrive over several
// turns, and a line built once would show whichever of them had landed first.
function showInCall(roomKnown) {
  const line = $('in-call');
  const val = webrtcDomains[browsingName] || {};
  const platform = (val.name || browsingName || '').replace(/\s*\(.*\)$/, '').trim();

  // Nothing about the conference until the room itself is known: a page that
  // cannot say which room it drives has no business naming what that room
  // joined.
  line.hidden = !menuDisplayed || !platform || !roomKnown;
  if (line.hidden) return;

  $('in-call-name').textContent = platform;
  $('in-call-room').textContent = currentRoom || '';
  $('in-call-room').hidden = !currentRoom;

  const icon = $('in-call-icon');
  const src = `${apiUrl('/logo')}/${encodeURIComponent(browsingName)}?gw_id=${encodeURIComponent(gwId)}`;
  if (icon.getAttribute('src') !== src) {
    icon.hidden = true;
    icon.onload = () => { icon.hidden = false; };
    icon.onerror = () => { icon.hidden = true; };
    icon.src = src;
  }
}

const capture = $('key-capture');
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
  // startPolling: the page leaves once the gateway reports the call over.
  return sendCommand('endCall', undefined, { startPolling: true });
}

// One request shape for every command. They differ only in what they send and
// whether the reply should start the status poll — sendKey and roomName only
// arm it on a submit key, since the gateway has nothing new to report until the
// entry is confirmed.
async function sendCommand(command, param1, { startPolling }) {
  const payload = { gw_id: gwId, payload: { command, param1 } };
  try {
    await fetch(apiUrl('/command'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    if (startPolling && !pollingStarted) { pollingStarted = true; setTimeout(checkGwStatus, 1000); }
  } catch (e) {
    // Nothing to announce: the switches are read back from the connector
    // either way, and the console has the detail.
    console.error('command failed:', command, e);
  }
}

// A submit key confirms an entry: only then is there something new to poll for.
const isSubmitKey = k => k === '#' || k === 'Enter';

async function sendKey(param1) {
  return sendCommand('sendKey', param1, {
    startPolling: isSubmitKey(param1),
  });
}

async function sendRoomName(param1) {
  return sendCommand('roomName', param1, {
    startPolling: isSubmitKey(param1),
  });
}

async function sendChat(message) {
  return sendCommand('sendChat', message, {
    startPolling: true,
  });
}


async function fetchIvrConfigAndRestoreState() {
  if (!gwId) return;
  const reveal = () => { $('wrap').style.visibility = 'visible'; };
  // Whatever happens — a screen drawn, an error, a gateway that never answers —
  // the page becomes visible. A safety net rather than a delay: 1.5s is well
  // past a normal load.
  const net = setTimeout(reveal, 1500);
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

    // The same response carries who is on the line. Reading it here rather than
    // waiting for the first poll is what keeps a reload from building itself in
    // stages: room, then conference, then logo, two seconds apart.
    roomName = statusData.data.peer_name || '';
    roomUri = statusData.data.peer_uri || '';
    // Awaited: it answers in about half a second, and it changes the name on
    // screen. Left to resolve on its own it would rewrite the line after the
    // page had been shown, which reads as one more step.
    if (roomName || roomUri) await fetchDisplayName();

    let bn = statusData.data.browsing;
    let rn = statusData.data.room;
    lastScreen = `${bn || ''}|${rn || ''}`;
    if (rn && bn) {
      menuOptions = (ivrMenus[bn] && ivrMenus[bn].options) ? ivrMenus[bn].options : [];
      menuDisplayed = true;
      currentRoom = rn;
      browsingName = bn;
      // Awaited: it reads the connector's state before drawing, so leaving it
      // to run on its own would reveal the page mid-build.
      await renderMenuOptions();
    } else {
      bn ? showInputAndPrepareMenu(bn) : renderDomainButtons();
    }
  } catch(e) {
    say('Error loading IVR config.');
  } finally {
    clearTimeout(net);
    reveal();
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
  showScreen('meeting');

  // The platform is recalled at the top: there is no way back to the list, the
  // gateway cannot return to its menu once a platform has been chosen.
  const val = webrtcDomains[selectedDomainKey] || {};
  const name = (val.name || selectedDomainKey).replace(/\s*\(.*\)$/, '').trim();
  $('chosen-name').textContent = name;
  const icon = $('chosen-icon');
  icon.alt = '';
  icon.hidden = true;
  icon.onload = () => { icon.hidden = false; };
  icon.onerror = () => { icon.hidden = true; };
  icon.src = `${apiUrl('/logo')}/${encodeURIComponent(selectedDomainKey)}?gw_id=${encodeURIComponent(gwId)}`;

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
    if (!statusRes.ok) { say(`Gateway unreachable (code ${statusRes.status}) — retrying…`); return setTimeout(checkGwStatus, POLL_MS * 5); }
    const statusData = await statusRes.json();
    // stopped: the container exited, the call is over. deleted: the VM is gone.
    // Either way there is nothing left to drive from here. The page used to
    // watch for "down", a value the proxy stopped writing when the states were
    // renamed.
    const state = statusData.data?.gw_state;
    if (state === "stopped" || state === "deleted") {
      say(currentLang === 'fr'
        ? 'L\u2019appel est termin\u00e9.'
        : 'The call has ended.');
      // a beat so the message is seen, then back to the pairing page
      setTimeout(() => { window.location.href = apiUrl('/pairing'); }, 800);
      return;
    }
    // The room this page drives, shown in the header.
    const peerName = statusData.data.peer_name || '';
    const peerUri = statusData.data.peer_uri || '';
    if (peerName !== roomName || peerUri !== roomUri) {
      const first = !roomName && !roomUri;
      roomName = peerName;
      roomUri = peerUri;
      showRoom();
      // Read once, when the endpoint first appears: the name it announced is
      // the starting point, whatever it had been set to before.
      if (first && (peerName || peerUri)) fetchDisplayName();
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
        currentRoom = rn;
        browsingName = bn;
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
    say('Status error — retrying…');
    return setTimeout(checkGwStatus, POLL_MS * 5);
  }
  // A control touched on the room tablet moves the same state as one touched
  // here, so the switches are read back on the poll rather than only after the
  // page's own commands.
  if (menuDisplayed) syncCtrlState();

  // Polling used to stop for good once the menu was drawn. The page then sat
  // on a call that had already ended, and never saw a platform picked from
  // the room keypad.
  setTimeout(checkGwStatus, POLL_MS);
}

// Which uiState field a command reflects, keyed on its icon: the digit and the
// label differ from one platform to the next, the icon does not. A command
// absent from here has no state to show and stays a button.
// The shapes the six known commands draw, and the words they say in either
// state. config.json gives one label per command — "Muet / Actif" — which names
// the action rather than the state: a switch needs to say what is, not what
// pressing it would do. A command not listed here keeps its config label and
// the icon the gateway serves.
const CTRL_SHAPE = {
  microphone_icon:   'M12 14a3 3 0 0 0 3-3V5a3 3 0 1 0-6 0v6a3 3 0 0 0 3 3zm5-3a5 5 0 0 1-10 0H5a7 7 0 0 0 6 6.9V21h2v-3.1A7 7 0 0 0 19 11h-2z',
  camera_icon:       'M17 10.5V7a1 1 0 0 0-1-1H4a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-3.5l4 4v-11l-4 4z',
  chat_icon:         'M20 2H4a2 2 0 0 0-2 2v18l4-4h14a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2z',
  hand_icon:         'M18 11V6a2 2 0 0 0-4 0V4a2 2 0 0 0-4 0v1a2 2 0 0 0-4 0v8l-1.6-1.6A2 2 0 0 0 1.6 14L6 20a5 5 0 0 0 4 2h6a5 5 0 0 0 5-5v-6a2 2 0 0 0-3 0z',
  participants_icon: 'M9 11a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7zm0 1.8c-3 0-6 1.5-6 3.4V19h12v-2.8c0-1.9-3-3.4-6-3.4zM17.5 11a3 3 0 1 0 0-6 3 3 0 0 0 0 6zm0 1.6c-.7 0-1.4.1-2 .3 1.3.9 2 2 2 3.3V19h5v-2.5c0-1.7-2.4-3-5-3z',
  info_icon:         'M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z',
};

// A slash says "nothing is going out" — it belongs on the microphone and the
// camera. A hidden panel is not a forbidden one, so chat, participants, info
// and the hand carry none: grey against green, with the words beside them,
// says enough.
const CTRL_SLASHED = ['microphone_icon', 'camera_icon'];

const CTRL_WORDS = {
  fr: {
    microphone_icon:   [['Micro coupé', 'Personne ne vous entend'], ['Micro actif', 'Vous êtes entendu']],
    camera_icon:       [['Caméra coupée', 'Votre image n\u2019est pas diffusée'], ['Caméra active', 'Votre image est diffusée']],
    chat_icon:         [['Chat masqué', 'Non affiché en salle'], ['Chat affiché', 'Visible sur l\u2019écran de la salle']],
    hand_icon:         [['Main baissée', 'Vous ne demandez pas la parole'], ['Main levée', 'Vous demandez la parole']],
    participants_icon: [['Participants masqués', 'Liste non affichée en salle'], ['Participants affichés', 'Liste visible sur l\u2019écran']],
    info_icon:         [['Informations masquées', 'Non affichées en salle'], ['Informations affichées', 'Visibles sur l\u2019écran']],
  },
  en: {
    microphone_icon:   [['Microphone off', 'Nobody can hear you'], ['Microphone on', 'You can be heard']],
    camera_icon:       [['Camera off', 'Your picture is not sent'], ['Camera on', 'Your picture is being sent']],
    chat_icon:         [['Chat hidden', 'Not shown in the room'], ['Chat shown', 'Visible on the room screen']],
    hand_icon:         [['Hand down', 'You are not asking to speak'], ['Hand raised', 'You are asking to speak']],
    participants_icon: [['Participants hidden', 'List not shown in the room'], ['Participants shown', 'List visible on the screen']],
    info_icon:         [['Details hidden', 'Not shown in the room'], ['Details shown', 'Visible on the screen']],
  },
};

// Writes a row's state into it: the class, the icon and the two lines. Called
// when the row is built and again on every read-back.
function paintCtrlRow(row, icon, on, fallbackLabel) {
  if (!row) return;
  row.classList.toggle('ctrl--on', on);
  row.querySelector('.ctrl__icon').innerHTML = ctrlIcon(icon, on);

  const words = (CTRL_WORDS[currentLang] || {})[icon];
  const state = row.querySelector('.ctrl__state');
  const hint = row.querySelector('.ctrl__hint');
  if (words) {
    state.textContent = words[on ? 1 : 0][0];
    hint.textContent = words[on ? 1 : 0][1];
  } else if (fallbackLabel !== undefined) {
    state.textContent = fallbackLabel;
  }
}

function ctrlIcon(icon, on) {
  const shape = CTRL_SHAPE[icon];
  if (!shape) return getIcon(icon);          // a command we do not know: the gateway's own
  // Two strokes: one in the page's background colour to carve a gap out of the
  // shape, the slash itself on top. On a solid icon a bare line would vanish
  // into it.
  const slash = !on && CTRL_SLASHED.includes(icon)
    ? '<path d="M3 1.6 22.4 21l-1.4 1.4L1.6 3z" class="ctrl__cut"/>' +
      '<path d="M3.6 2.3 21.7 20.4l-1.3 1.3L2.3 3.6z"/>' : '';
  return `<svg viewBox="0 0 24 24" aria-hidden="true">${'<path d="' + shape + '"/>'}${slash}</svg>`;
}

const CTRL_STATE = {
  microphone_icon:   (ui) => ui.media && ui.media.microphone,
  camera_icon:       (ui) => ui.media && ui.media.camera,
  chat_icon:         (ui) => ui.panels && ui.panels.chat,
  hand_icon:         (ui) => ui.panels && ui.panels.handRaised,
  participants_icon: (ui) => ui.panels && ui.panels.participants,
  info_icon:         (ui) => ui.panels && ui.panels.info,
};

// The five every connector offers. What comes after is its own, and is drawn
// as plain buttons below the chat row.
const CTRL_COMMON = Object.keys(CTRL_STATE);

// The same four the room tablet offers, out of the eight the connector knows.
const REACTIONS = [
  ['thumbs-up', '\u{1F44D}'],
  ['clapping-hands', '\u{1F44F}'],
  ['red-heart', '\u2764\uFE0F'],
  ['face-with-tears-of-joy', '\u{1F602}'],
];

// The conference the gateway has joined, as the status poll reports it.
let currentRoom = '';

// Last state read from the connector, or null on one that reports none.
let ctrlState = null;

async function fetchCtrlState() {
  if (!gwId) return null;
  try {
    const res = await fetch(apiUrl('/command'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ gw_id: gwId, payload: { command: 'uiState', param1: '' } }),
    });
    if (!res.ok) return null;
    const json = await res.json();
    return json?.data?.uiState || null;
  } catch (e) {
    return null;
  }
}

// Reads the connector's state and moves the switches onto it. Called after
// every command, since most of them toggle on the far side: without the
// read-back a switch would show what it assumed rather than what happened.
async function syncCtrlState() {
  const ui = await fetchCtrlState();
  ctrlState = ui;
  if (!ui) return;
  // The switch is not the only thing that says what the state is: the words
  // and the icon say it too, and moving one without the others leaves the row
  // contradicting itself.
  document.querySelectorAll('.ctrl__switch[data-icon]').forEach((sw) => {
    const icon = sw.dataset.icon;
    const probe = CTRL_STATE[icon];
    if (!probe) return;
    const on = probe(ui) === true;
    sw.checked = on;
    paintCtrlRow(sw.closest('.ctrl'), icon, on);
  });
}

async function renderMenuOptions() {
  const list = $('ctrl-list');
  const more = $('ctrl-more');
  list.innerHTML = '';
  more.innerHTML = '';
  // Nothing to draw: leave the screens as they are rather than switching to an
  // empty one, which would show the platform line with no platform behind it.
  if (!menuOptions.length) return;

  showScreen(null);
  menuDisplayed = true;
  // showRoom may have run just before this, while menuDisplayed was still
  // false, and hidden the line on that basis. Nothing else would bring it back
  // until the room details next change.
  showInCall(!!(roomName || roomUri));

  // Read the state before drawing, so a switch never appears in the wrong
  // position and then corrects itself under the visitor's eyes.
  ctrlState = await fetchCtrlState();

  // Reactions ride on the same command set as the switches: a connector that
  // reports its state is one that implements them. There is no capability list
  // to ask, so their presence follows from that rather than from a guess.
  const reactionRow = $('reactions');
  reactionRow.hidden = !ctrlState;
  if (ctrlState && !reactionRow.childElementCount) {
    for (const [name, glyph] of REACTIONS) {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'reaction';
      btn.textContent = glyph;
      btn.setAttribute('aria-label', name);
      btn.onclick = () => sendCommand('reaction', name, {
        startPolling: false,
      });
      reactionRow.appendChild(btn);
    }
  }

  let hasChat = false;

  for (const opt of menuOptions) {
    const icon = String(opt.icon || '');
    const label = opt[currentLang] || opt['en'] || '';
    const probe = CTRL_STATE[icon];
    const common = CTRL_COMMON.includes(icon);
    if (icon.toLowerCase().includes('chat')) hasChat = true;

    if (probe && ctrlState) {
      const on = probe(ctrlState) === true;

      const row = document.createElement('label');
      row.className = 'ctrl';
      row.innerHTML = '<span class="ctrl__icon"></span>' +
                      '<span class="ctrl__text"><span class="ctrl__state"></span>' +
                      '<span class="ctrl__hint"></span></span>';
      paintCtrlRow(row, icon, on, label);

      const sw = document.createElement('input');
      sw.type = 'checkbox';
      sw.className = 'ctrl__switch';
      sw.dataset.icon = icon;
      sw.checked = on;
      sw.addEventListener('change', async () => {
        await sendKey(opt.dtmf);
        await syncCtrlState();
      });

      row.appendChild(sw);
      list.appendChild(row);
    } else {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'ctrl';
      // Same shape as a switch row, one line instead of two: the connector
      // says nothing about this command's state, so the config label stands
      // on its own.
      btn.innerHTML = `<span class="ctrl__icon">${ctrlIcon(icon, true)}</span>` +
                      '<span class="ctrl__text"><span class="ctrl__state"></span></span>';
      btn.querySelector('.ctrl__state').textContent = label;
      btn.onclick = async () => {
        await sendKey(opt.dtmf);
        await syncCtrlState();
      };
      (common ? list : more).appendChild(btn);
    }
  }

  // The chat row sits under the commands rather than among them: typing a
  // message is a different gesture from pressing a control.
  const chatRow = $('chat-row');
  chatRow.hidden = !hasChat;
  if (hasChat) {
    $('chat-input').placeholder = TEXTS[currentLang].chatPlaceholder;
    $('chat-send').textContent = TEXTS[currentLang].chatSend;
  }

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
    await sendRoomName(capture.value);
    await captureReset();
    await setTimeout(() => sendKey('#'), 450);
  }
};
// One dialog for every question the page asks. The browser's own confirm()
// sits at the top of the window, out of the page and out of its styling, so
// this one carries the text and the action it is asked for.
let confirmAction = null;
let confirmReturnTo = null;

function ask(message, actionLabel, onYes, returnTo) {
  $('confirm-body').textContent = message;
  $('confirm-yes').textContent = actionLabel;
  $('confirm-yes').disabled = false;
  confirmAction = onYes;
  confirmReturnTo = returnTo || null;
  $('confirm').hidden = false;
  $('confirm-no').focus();
}

function closeConfirm() {
  $('confirm').hidden = true;
  confirmAction = null;
  if (confirmReturnTo) confirmReturnTo.focus();
  confirmReturnTo = null;
}

function askToHangUp() {
  const t = TEXTS[currentLang];
  ask(t.confirmBody, t.confirmYes, async () => {
    $('confirm-yes').disabled = true;
    $('btn-endcall').disabled = true;
    leaving = true;
    await sendEndCall();
    setTimeout(() => { window.location.href = apiUrl('/pairing'); }, 250);
  }, $('btn-endcall'));
}

$('chat-send').onclick = async () => {
  const v = $('chat-input').value.trim();
  if (!v) return;
  await sendChat(v);
  $('chat-input').value = '';
  await syncCtrlState();     // sending opens the chat panel on some connectors
};
$('chat-input').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') { e.preventDefault(); $('chat-send').click(); }
});

$('name-edit').onclick = startEditName;
$('name-cancel').onclick = stopEditName;
$('name-save').onclick = async () => {
  const value = $('name-input').value.trim();
  stopEditName();
  if (value) await sendDisplayName(value);
};
$('name-input').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') { e.preventDefault(); $('name-save').click(); }
  if (e.key === 'Escape') { e.preventDefault(); stopEditName(); }
});

$('btn-endcall').onclick = askToHangUp;
$('confirm-no').onclick = closeConfirm;
$('confirm-close').onclick = closeConfirm;
$('confirm-backdrop').onclick = closeConfirm;
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape' && !$('confirm').hidden) closeConfirm();
});

// Runs whatever ask() was given, rather than one action written in here: the
// dialog now serves every question the page puts.
$('confirm-yes').onclick = () => {
  const action = confirmAction;
  closeConfirm();
  if (action) action();
};
// slideShot button bindings
$('btn-slideShot').onclick = async () => { await sendSlideShot(); };
$('slide-close').onclick = () => { hideSlidePreview(); };

function showSlidePreview(b64) {
  const panel = $('slide-preview');
  const img = $('slide-img');
  const dl = $('slide-download');
  if (!panel || !img || !dl) return;
  const dataUrl = `data:image/png;base64,${b64}`;
  img.src = dataUrl;
  dl.href = dataUrl;
  dl.download = `slide_${Date.now()}.png`;
  updateFullscreenButtonLabel();
  panel.style.display = 'flex';
  panel.setAttribute('aria-hidden', 'false');
  $('slide-backdrop').style.display = 'block';
  $('slide-backdrop').setAttribute('aria-hidden', 'false');
}

function hideSlidePreview() {
  const panel = $('slide-preview');
  if (!panel) return;
  if (document.fullscreenElement) {
    document.exitFullscreen().catch(()=>{});
  }
   panel.style.display = 'none';
   panel.setAttribute('aria-hidden', 'true');
   $('slide-img').src = '';
   $('slide-backdrop').style.display = 'none';
   $('slide-backdrop').setAttribute('aria-hidden', 'true');
}

// Append a thumbnail to the gallery and wire click -> preview
function addSlideThumbnail(b64) {
  const gallery = $('slide-gallery');
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
   const btn = $('btn-slideShot');
   const payload = { gw_id: gwId, payload: { command: "slideShot" } };
   if (btn) { btn.disabled = true; }
   try {
     const res = await fetch(apiUrl('/command'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
     const json = await res.json();
     if (!res.ok || !json.data || !json.data.slideImg) {
       throw new Error(json.error?.message || 'No image returned');
     }
    // add to gallery and show preview for the new capture
    addSlideThumbnail(json.data.slideImg);
    showSlidePreview(json.data.slideImg);
   } catch (e) {
     // The one failure worth a word is the ordinary one: nothing on screen to
     // capture. Anything else is a fault, and the console has its detail.
     const t = TEXTS[currentLang];
     say(/no image/i.test(e.message) ? t.captureNone : t.captureFail);
     console.error('capture failed:', e);
   } finally {
     if (btn) { btn.disabled = false; }
   }
 }

// toggle fullscreen using Fullscreen API
function updateFullscreenButtonLabel() {
  const fsBtn = $('slide-fullscreen');
  if (!fsBtn) return;
  const isFs = !!document.fullscreenElement;
  const t = TEXTS[currentLang];
  fsBtn.innerHTML = isFs ? ICON_SHRINK : ICON_EXPAND;
  fsBtn.setAttribute('aria-label', isFs ? t.slideShrink : t.slideFullscreen);
  fsBtn.dataset.tip = isFs ? t.slideShrink : t.slideFullscreen;
  const unused = isFs
    ? (currentLang === 'fr' ? 'Quitter' : 'Exit')
    : (currentLang === 'fr' ? 'Agrandir' : 'Full screen');
}

async function toggleFullscreen() {
  const panel = $('slide-preview');
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
$('slide-fullscreen').onclick = () => { toggleFullscreen(); };

// wire discard button: remove matching thumbnail(s) from gallery then close preview
$('slide-discard').onclick = () => {
  const img = $('slide-img');
  if (!img || !img.src) return;
  const t = TEXTS[currentLang];
  ask(t.discardBody, t.slideDiscard, () => discardSlide(img), $('slide-discard'));
};

function discardSlide(img) {
  const gallery = $('slide-gallery');
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
