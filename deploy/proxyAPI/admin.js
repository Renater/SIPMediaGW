'use strict';

/* Gateway Manager — read-only console served by the proxy on /admin/.
   No authentication logic here: the browser holds the Basic credentials
   for this realm and re-sends them on every same-origin request. */

const CONFIG = Object.freeze({
  endpoint: '/admin/statuses',
  pilotUrl: '/interact?gwId=',
  iconUrl: '/admin/icons/',
  refreshMs: 10000,
  langKey: 'sipmediagw.admin.lang',   // UI preference only, no secret
});

/* Older proxies leak the literal string "None" for unset fields. */
const norm = v => (v == null || v === '' || v === 'None') ? null : v;

/* ---------------------------------------------------------------- i18n */

const I18N = {
  fr: {
    subtitle: 'supervision temps réel des passerelles SIPMediaGW', refresh: 'Actualiser', auto: 'auto 10 s',
    countdown: s => `(${s})`, updated: 'Mis à jour à', search: 'Rechercher par ID, terminal, réunion, code, passerelle…',
    shown: (n, total) => `${n} / ${total} passerelle${total > 1 ? 's' : ''}`,
    tiles: { total: 'enregistrées', free: 'slots libres', idle: 'en attente d’appel', ivr: 'en IVR', call: 'en conférence' },
    cols: ['ID', 'Type', 'État', 'Nom affiché', 'URI SIP', 'Réunion', 'Plateforme', 'Durée', 'Code', 'Passerelle', ''],
    states: { free: 'Slot libre', idle: 'En attente d’appel', ivr: 'IVR', call: 'En conférence' },
    types: { baresip: 'Visio', recording: 'Enreg.', streaming: 'Diffusion' },
    control: 'Contrôle', copied: 'Copié', copyFail: 'Copie impossible',
    empty: 'Aucune passerelle enregistrée.', noMatch: 'Aucune passerelle ne correspond à la recherche.',
    err401: 'Session expirée — rechargez la page pour vous ré-identifier.', errLoad: 'Chargement impossible',
  },
  en: {
    subtitle: 'live supervision of registered SIPMediaGW gateways', refresh: 'Refresh', auto: 'auto 10 s',
    countdown: s => `(${s})`, updated: 'Updated at', search: 'Search by ID, endpoint, meeting, code, gateway…',
    shown: (n, total) => `${n} of ${total} gateway${total > 1 ? 's' : ''}`,
    tiles: { total: 'registered', free: 'free slots', idle: 'waiting for a call', ivr: 'in IVR', call: 'in conference' },
    cols: ['ID', 'Type', 'State', 'Display name', 'SIP URI', 'Meeting', 'Platform', 'Call time', 'Code', 'Gateway', ''],
    states: { free: 'Free slot', idle: 'Waiting for a call', ivr: 'IVR', call: 'In conference' },
    types: { baresip: 'Video', recording: 'Recording', streaming: 'Streaming' },
    control: 'Control', copied: 'Copied', copyFail: 'Copy failed',
    empty: 'No gateway registered.', noMatch: 'No gateway matches the search.',
    err401: 'Session expired — reload the page to sign in again.', errLoad: 'Could not load',
  },
};

/* Connector key (browsing field) → display name; served as /admin/icons/<key>. */
const PLATFORMS = {
  jitsi: 'Jitsi', visio: 'Visio', webinaire: 'Webinaire', bigbluebutton: 'BigBlueButton', bbbesr: 'BBB ESR',
  livekit: 'LiveKit', teams: 'Teams', googlemeet: 'Google Meet', nextcloud: 'Nextcloud Talk',
};

let lang = (() => {
  const saved = localStorage.getItem(CONFIG.langKey);
  if (saved in I18N) return saved;
  return (navigator.language || 'en').toLowerCase().startsWith('fr') ? 'fr' : 'en';
})();
let t = I18N[lang];

/* ----------------------------------------------------------- helpers */

const $ = id => document.getElementById(id);
const esc = s => String(s).replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const dash = '<span class="dim">—</span>';
const cell = v => v == null ? dash : esc(v);
/* Copiable value: plain text shown, raw value carried for the clipboard. */
const copyable = (v, cls = '') => v == null ? dash : `<span class="copy ${cls}" data-copy="${esc(v)}">${esc(v)}</span>`;
/* The gateway field is the launcher address "host:port"; the port is fixed. */
const hostOf = v => { const s = norm(v); return s == null ? null : s.replace(/:\d+$/, ''); };

/* Derived state. "status" alone is ambiguous: "started" is a free slot
   (container stopped, allocatable by /start) and "working" only means the
   container runs. A SIP peer with no room yet is in the IVR; a room (with
   or without a peer, browsing-only gateways) means in conference. */
function derive(g) {
  const peer = !!(norm(g.call_started) || norm(g.peer_uri));
  const room = !!norm(g.room);
  if (g.status === 'started') return 'free';
  if (g.status === 'working') return room ? 'call' : (peer ? 'ivr' : 'idle');
  return 'other';
}

function pill(kind, raw) {
  return `<span class="pill ${kind}">${esc(t.states[kind] || raw || '?')}</span>`;
}

function typeBadge(raw) {
  const v = norm(raw);
  return v == null ? dash : `<span class="type">${esc(t.types[v] || v)}</span>`;
}

function platformCell(key) {
  const k = norm(key);
  if (!k) return dash;
  const name = PLATFORMS[k] || k;
  const icon = /^[a-z0-9]+$/.test(k) ? `<img src="${CONFIG.iconUrl}${k}" alt="" data-fallback="1">` : '';
  return `<span class="platform">${icon}<span>${esc(name)}</span></span>`;
}

function duration(startedIso) {
  const start = Date.parse(startedIso);        // ISO 8601, "Z" suffix honoured
  if (Number.isNaN(start)) return null;
  const sec = Math.max(0, Math.floor((Date.now() - start) / 1000));
  const h = Math.floor(sec / 3600), m = Math.floor(sec % 3600 / 60), s = sec % 60;
  const p = n => String(n).padStart(2, '0');
  return `${p(h)}:${p(m)}:${p(s)}`;
}

/* Call time column: live SIP call duration for video gateways; recorded or
   streamed media duration (and transcript progress) for the other types. */
function timeCell(g) {
  const started = norm(g.call_started);
  if (started) return `<span class="num">${esc(duration(started) || '')}</span>`;
  const media = norm(g.media_duration), pct = norm(g.transcript_progress);
  if (media && media !== '0') {
    const sub = pct && pct !== '0' ? `<div class="sub">${esc(pct)} %</div>` : '';
    return `<span class="num">${esc(media)}</span>${sub}`;
  }
  return dash;
}

/* Text used by the search box: everything a human might paste from a log. */
function haystack(id, g) {
  return [id, g.gateway, g.type, g.room, g.browsing, g.peer_uri, g.peer_name, g.pairing_code]
    .map(norm).filter(Boolean).join(' ').toLowerCase();
}

/* ------------------------------------------------------------ render */

let data = null, nextRefreshAt = 0, refreshTimer = null;

function applyLanguage() {
  t = I18N[lang];
  document.documentElement.lang = lang;
  $('subtitle').textContent = t.subtitle;
  $('refresh').textContent = t.refresh;
  $('lang').textContent = lang === 'fr' ? 'EN' : 'FR';
  $('lAuto').textContent = t.auto;
  $('search').placeholder = t.search;
  for (const k of ['total', 'free', 'idle', 'ivr', 'call']) {
    $('l' + k[0].toUpperCase() + k.slice(1)).textContent = t.tiles[k];
  }
  $('head').innerHTML = t.cols.map(c => `<th>${esc(c)}</th>`).join('');
  render();
}

function render() {
  if (!data) return;
  const ids = Object.keys(data).sort();
  const kinds = Object.fromEntries(ids.map(id => [id, derive(data[id])]));
  $('nTotal').textContent = ids.length;
  for (const k of ['free', 'idle', 'ivr', 'call']) {
    $('n' + k[0].toUpperCase() + k.slice(1)).textContent = ids.filter(id => kinds[id] === k).length;
  }

  const q = $('search').value.trim().toLowerCase();
  const shown = q ? ids.filter(id => haystack(id, data[id]).includes(q)) : ids;
  $('shown').textContent = ids.length ? t.shown(shown.length, ids.length) : '';

  if (!ids.length) { $('rows').innerHTML = `<tr><td colspan="11" class="msg">${esc(t.empty)}</td></tr>`; return; }
  if (!shown.length) { $('rows').innerHTML = `<tr><td colspan="11" class="msg">${esc(t.noMatch)}</td></tr>`; return; }

  $('rows').innerHTML = shown.map(id => {
    const g = data[id], kind = kinds[id];
    const control = kind === 'free' ? '' :
      `<a class="btn" href="${CONFIG.pilotUrl}${encodeURIComponent(id)}" target="_blank" rel="noopener">${esc(t.control)}</a>`;
    return `<tr>
      <td>${copyable(id, 'mono')}</td>
      <td>${typeBadge(g.type)}</td>
      <td>${pill(kind, g.status)}</td>
      <td>${copyable(norm(g.peer_name))}</td>
      <td>${copyable(norm(g.peer_uri), 'mono')}</td>
      <td>${copyable(norm(g.room), 'mono')}</td>
      <td>${platformCell(g.browsing)}</td>
      <td>${timeCell(g)}</td>
      <td>${copyable(norm(g.pairing_code), 'mono')}</td>
      <td>${copyable(hostOf(g.gateway), 'mono')}</td>
      <td>${control}</td>
    </tr>`;
  }).join('');

  // Missing icon (unknown connector or icons directory not mounted): drop it.
  for (const img of $('rows').querySelectorAll('img[data-fallback]')) {
    img.addEventListener('error', () => img.remove(), { once: true });
  }
}

/* ------------------------------------------------------- clipboard */

let toastTimer = null;
function toast(msg) {
  const el = $('toast');
  el.textContent = msg; el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 1400);
}

/* navigator.clipboard only exists in secure contexts (HTTPS / localhost);
   plain-HTTP deployments fall back to the legacy execCommand path. */
async function copyText(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
    } else {
      const ta = document.createElement('textarea');
      ta.value = text; ta.setAttribute('readonly', '');
      ta.style.position = 'fixed'; ta.style.opacity = '0';
      document.body.appendChild(ta); ta.select();
      const ok = document.execCommand('copy');
      ta.remove();
      if (!ok) throw new Error('execCommand');
    }
    toast(`${t.copied} : ${text}`);
  } catch (e) {
    toast(t.copyFail);
  }
}

$('rows').addEventListener('click', e => {
  const el = e.target.closest('.copy');
  if (el) copyText(el.dataset.copy);
});

/* -------------------------------------------------------------- load */

async function load() {
  $('refresh').disabled = true;
  try {
    const res = await fetch(CONFIG.endpoint, { headers: { 'Accept': 'application/json' } });
    if (res.status === 401) {
      $('rows').innerHTML = `<tr><td colspan="11" class="msg err">${esc(t.err401)}</td></tr>`;
      return;
    }
    if (!res.ok) throw new Error('HTTP ' + res.status);
    data = await res.json();
    render();
    $('stamp').textContent = `${t.updated} ${new Date().toLocaleTimeString()}`;
  } catch (e) {
    $('rows').innerHTML = `<tr><td colspan="11" class="msg err">${esc(t.errLoad)} (${esc(e.message)})</td></tr>`;
    $('stamp').textContent = '';
  } finally {
    $('refresh').disabled = false;
    nextRefreshAt = Date.now() + CONFIG.refreshMs;
  }
}

function tick() {
  if (data) render();                          // live call durations
  if ($('auto').checked && nextRefreshAt) {
    $('countdown').textContent = t.countdown(Math.max(0, Math.ceil((nextRefreshAt - Date.now()) / 1000)));
  } else {
    $('countdown').textContent = '';
  }
}

function schedule() {
  clearInterval(refreshTimer);
  if ($('auto').checked) {
    nextRefreshAt = Date.now() + CONFIG.refreshMs;
    refreshTimer = setInterval(load, CONFIG.refreshMs);
  } else {
    nextRefreshAt = 0;
  }
  tick();
}

$('refresh').addEventListener('click', load);
$('auto').addEventListener('change', schedule);
$('search').addEventListener('input', render);
$('lang').addEventListener('click', () => {
  lang = lang === 'fr' ? 'en' : 'fr';
  localStorage.setItem(CONFIG.langKey, lang);
  applyLanguage();
});

applyLanguage();
load();
schedule();
setInterval(tick, 1000);
