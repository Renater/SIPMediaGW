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

// defined early so the startup callback below can call it
function updateSlideControlsVisibility() {
  const ctrl = document.getElementById('slide-controls');
  if (!ctrl) return;
  const inputRow = document.getElementById('input-row');
  const isInputVisible = inputRow && getComputedStyle(inputRow).display !== 'none';
  // show only when menuDisplayed (in the meeting) and not in "input name" phase
  ctrl.style.display = (menuDisplayed && !isInputVisible) ? 'flex' :
                       'none';
}

function getRoomNamePlaceholder() {
  const captureEl = document.getElementById('key-capture');
  if (!captureEl) return '';
  const selectedInfo = browsingName && roomNameInfo[browsingName] ? roomNameInfo[browsingName] : null;
  const lang = currentLang === 'fr' ? 'fr' : 'en';
  const fallback = lang === 'fr' ? 'Entrez le nom de la réunion' : 'Enter the meeting name';
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

  const labelEl = document.getElementById('input-label');
  if (labelEl) {
    labelEl.textContent = currentLang === 'fr' ? 'Nom de la réunion' : 'Meeting Name';
  }

  captureEl.placeholder = captureEl.value ? '' : placeholder;
  if (hintEl) {
    hintEl.textContent = hint;
    hintEl.style.display = hint ? 'block' : 'none';
  }
}

function renderLangSwitch() {
  const langDiv = document.getElementById('lang-switch');
  langDiv.innerHTML = `
    <button onclick="setMenuLang('fr')" ${currentLang === 'fr' ? 'disabled' : ''}>🇫🇷 Français</button>
    <button onclick="setMenuLang('en')" ${currentLang === 'en' ? 'disabled' : ''}>🇬🇧 English</button>
  `;
  // use Meeting Name / Nom de la réunion
  document.getElementById('input-label').textContent = currentLang === 'fr' ? 'Nom de la réunion' : 'Meeting Name';
  document.getElementById('btn-enter').textContent = currentLang === 'fr' ? 'Entrée' : 'Enter';
  const enterBtn = document.getElementById('btn-enter');
  if (enterBtn) enterBtn.title = currentLang === 'fr' ? 'Envoyer le nom de la réunion' : 'Send meeting name';
  const delBtn = document.getElementById('btn-del');
  if (delBtn) delBtn.title = currentLang === 'fr' ? 'Envoyer la touche étoile' : 'Send star key';
  const endBtn = document.getElementById('btn-endcall');
  if (endBtn) endBtn.textContent = currentLang === 'fr' ? 'Fin d’appel' : 'End call';
  if (endBtn) endBtn.title = currentLang === 'fr' ? 'Mettre fin à l’appel' : 'End the call';
  const ss = document.getElementById('btn-slideShot');
  if (ss) ss.textContent = currentLang === 'fr' ? 'Capture' : 'Capture';
  const dl = document.getElementById('slide-download');
  if (dl) dl.textContent = currentLang === 'fr' ? 'Télécharger' : 'Download';
  const cl = document.getElementById('slide-close');
  if (cl) cl.textContent = currentLang === 'fr' ? 'Fermer' : 'Close';
  const fs = document.getElementById('slide-fullscreen');
  if (fs) fs.textContent = currentLang === 'fr' ? 'Agrandir' : 'Full screen';
  const dis = document.getElementById('slide-discard');
  if (dis) dis.textContent = currentLang === 'fr' ? 'Supprimer' : 'Discard';
  // translate display-name label as well
  const dlab = document.getElementById('display-label');
  if (dlab) dlab.textContent = currentLang === 'fr' ? 'Nom affiché' : 'Display Name';
  updateRoomNameInputUi();
}
function setMenuLang(lang) {
  currentLang = lang;
  renderLangSwitch();
  if (menuDisplayed) {
    renderMenuOptions();
  } else if (browsingName) {
    // If a domain is already selected, do not return to the domain list.
    // If options are already present, display them in the correct language;
    // otherwise, display the input field.
    if (menuOptions && menuOptions.length) {
      renderMenuOptions();
      menuDisplayed = true;
      const inputRow = document.getElementById('input-row');
      if (inputRow) inputRow.style.display = 'flex';
    } else {
      showInputAndPrepareMenu(browsingName);
    }
  } else {
    renderDomainButtons();
  }
}

const capture = document.getElementById('key-capture');
updateRoomNameInputUi();

function captureReset() {
  capture.value = '';
  updateRoomNameInputUi();
}

// Display name input references and helpers
const displayInput = document.getElementById('display-name');
const displayLabel = document.getElementById('display-label');
if (displayInput) {
  displayInput.placeholder = currentLang === 'fr' ? 'Nom affiché' : 'Display name';
  displayInput.disabled = true; // disabled until fetched
}

async function sendDisplayName(name) {
  if (!gwId) return;
  const status = document.getElementById('status');
  const log = document.getElementById('log');
  const payload = { gw_id: gwId, payload: { command: "displayName", param1: name } };
  if (status) status.textContent = currentLang === 'fr' ? 'Envoi: nom affiché…' : 'Sending: display name…';
  if (log) log.textContent = `→ POST ${apiUrl('/command')}\n   ${JSON.stringify(payload)}`;
  try {
    const res = await fetch(apiUrl('/command'), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const text = await res.text();
    if (status) status.textContent = `✓ ${res.status} — display name`;
    if (log) log.textContent += `\n← ${res.status} ${text.slice(0,120)}`;
  } catch (e) {
    if (status) status.textContent = `✗ Display name error`;
    if (log) log.textContent += `\n← ${e.message}`;
  }
}

capture.addEventListener('input', function() {
  this.placeholder = this.value ? '' : getRoomNamePlaceholder();
});
capture.addEventListener('keydown', async function(e) {
  if (e.key === 'Enter') {
    e.preventDefault();
    await sendDisplayName(displayInput.value.trim());
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

async function fetchDisplayName() {
  if (!gwId) return;
  displayInput.disabled = true;
  try {
    const res = await fetch(apiUrl('/command'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ gw_id: gwId, payload: { command: 'displayName' } })
    });
    if (!res.ok) return;
    const json = await res.json();
    const name = json?.data?.displayName || json?.data?.displayname || '';
    displayInput.value = name || '';
  } catch (e) {
    console.error('fetchDisplayName error', e);
  } finally {
    displayInput.disabled = false;
  }
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
  const menuDiv = document.getElementById('menu-options');
  menuDiv.innerHTML = '';
  const domains = Object.entries(webrtcDomains);
  if (!domains.length) return;

  // ensure we're not considered "in the menu" (no slide controls)
  menuDisplayed = false;
  updateSlideControlsVisibility();

  document.getElementById('input-row').style.display = 'none';

  const chooseLabel = currentLang === 'fr' ? 'Choisissez un service :' : 'Choose a service:';
  menuDiv.innerHTML = `<div style="margin-bottom:0.5em;width:100%;">${chooseLabel}</div>`;

  domains.forEach(([key, val], idx) => {
    const digit = (idx + 1).toString();
    const btn = document.createElement('button');
    btn.className = 'key menu-key domain-btn';
    btn.title = `Press ${digit}`;
    // prefer explicit domain if provided, otherwise try to extract from name in parentheses
    const rawName = val.name || key;
    const nameOnly = rawName.replace(/\s*\(.*\)$/, '').trim();
    let host = val.domain || '';
    if (!host) {
      const m = rawName.match(/\(([^)]+)\)\s*$/);
      host = m ? m[1] : '';
    }
    const hostHtml = host ? `<span class="domain-host">(${host})</span>` : '';
    btn.innerHTML = `
      <img src="${apiUrl('/logo')}/${encodeURIComponent(key)}?gw_id=${encodeURIComponent(gwId)}"
           alt="" onerror="if(!this.dataset.fallbackTried){this.dataset.fallbackTried='true';this.src='./images/domain-icons/${encodeURIComponent(key)}.png'}">
      <div class="domain-text"><span class="domain-name">${nameOnly}</span>${hostHtml}</div>
    `;
    btn.onclick = async () => { await sendKey(digit); await sendKey('#'); showInputAndPrepareMenu(key); };
    menuDiv.appendChild(btn);
  });

  document.getElementById('key-capture').disabled = !browsingName;
}

function showInputAndPrepareMenu(selectedDomainKey) {
  browsingName = selectedDomainKey;
  menuOptions = [];
  // entering input phase — not the menu yet
  menuDisplayed = false;
  renderMenuOptions();
  // show the input row when preparing the menu / input
  const inputRow = document.getElementById('input-row');
  if (inputRow) inputRow.style.display = 'flex';

  document.getElementById('key-capture').disabled = false;
  updateRoomNameInputUi();
  // Focus logic: prefer focusing the display-name field if it's empty,
  // otherwise focus the key-capture input so user can type meeting code quickly.
  // Do NOT steal focus if the user is already interacting with one of the inputs.
  const captureEl = document.getElementById('key-capture');
  const displayEl = document.getElementById('display-name');
  try {
    const active = document.activeElement;
    const inputsContainer = document.getElementById('inputs');
    const userIsInteracting = active &&
                              inputsContainer &&
                              inputsContainer.contains(active) &&
                              (active.tagName === 'INPUT' || active.tagName === 'TEXTAREA' || active.isContentEditable);
    if (!userIsInteracting) {
      if (displayEl && !displayEl.value.trim()) { displayEl.focus(); }
      else if (captureEl) { captureEl.focus(); }
    }
  } catch (e) { /* ignore focus errors */ }

  // update slide controls visibility (hide during input)
  updateSlideControlsVisibility();
}

async function checkGwStatus() {
  if (!gwId) return setTimeout(checkGwStatus, POLL_MS);
  try {
    const statusRes = await fetch(apiUrl('/status') + `?gw_id=${encodeURIComponent(gwId)}`);
    // A transient failure must not silence the page for good: it keeps
    // polling, more slowly, so a passing outage is recovered from.
    if (!statusRes.ok) { document.getElementById('status').textContent = `Gateway unreachable (code ${statusRes.status}) — retrying…`; return setTimeout(checkGwStatus, POLL_MS * 5); }
    const statusData = await statusRes.json();
    if (statusData.data?.gw_state === "down") {
      document.getElementById('status').textContent = `Gateway down ("exited") — Returning to interact…`;
      // small delay so user sees message, then return to interact root (no gwId)
      setTimeout(() => { window.location.href = apiUrl('/pairing'); }, 800);
      return;
    }
    let bn = statusData.data.browsing;
    let rn = statusData.data.room;

    // The gateway is the source of truth: the platform and the conference id
    // can be entered on the endpoint keypad just as well as here, so the
    // screen follows the reported state instead of what this page last did.
    const screen = `${bn || ''}|${rn || ''}`;
    if (screen !== lastScreen) {
      lastScreen = screen;
      if (rn && bn) {
        menuOptions = (ivrMenus[bn] && ivrMenus[bn].options) ? ivrMenus[bn].options : [];
        menuDisplayed = true;
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

  const inputRow = document.getElementById('input-row');
  if (inputRow) inputRow.style.display = 'none';

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

onReady(() => {
  fetchIvrConfigAndRestoreState();
  fetchDisplayName();
  // call after initial render to hide slide-controls when appropriate
  updateSlideControlsVisibility();
  // Polling used to start only once the user had pressed something, so a page
  // opened on an idle gateway never noticed the room joining a conference.
  if (!pollingStarted) { pollingStarted = true; setTimeout(checkGwStatus, POLL_MS); }
});
document.getElementById('btn-enter').onclick = async () => {
  await sendDisplayName(displayInput.value.trim());
  if (capture.value.length > 0) {
    //await sendString(capture.value + '#');
    await sendRoomName(capture.value);
    await captureReset();
    await setTimeout(() => sendKey('#'), 450);
  }
};
document.getElementById('btn-del').onclick = () => {
  sendKey('*');
};
document.getElementById('btn-endcall').onclick = async () => {
  // a small confirmation to avoid accidental hangups
  const confirmMsg = currentLang === 'fr' ? "Terminer l'appel ?" : "End the call?";
  if (confirm(confirmMsg)) {
    // visually disable while sending
    const b = document.getElementById('btn-endcall');
    if (b) { b.disabled = true; }
    await sendEndCall();
    // keep disabled briefly while redirecting
    // small delay so user sees result, then back to the pairing page
    setTimeout(() => { window.location.href = apiUrl('/pairing'); }, 250);
  }
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
