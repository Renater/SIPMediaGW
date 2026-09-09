// ---------------------------------------------------------------------------
// Per-deployment settings. The service is white-labelled — VisioHub at RENATER,
// Visiby Connect on NUBO — so the name, the logo and the documentation link are
// gathered here rather than scattered through the markup.
// ---------------------------------------------------------------------------
const BRAND = {
  name: 'SIPMediaGW',
  tagline: '',
  logo: '',                       // e.g. '/pairing/static/logo.svg'; empty hides it
  docUrl: '',                     // empty hides the documentation link
  docLabelFr: 'Documentation et présentation du service',
  docLabelEn: 'Service documentation and overview',
};

const CODE_LENGTH = 5;

const TEXTS = {
  fr: {
    title: 'Contrôler votre réunion',
    subtitle: "Saisissez le code affiché à l'écran",
    button: 'Valider',
    hintTitle: 'Où trouver le code ?',
    hint: "Ce code à 5 caractères s'affiche sur l'écran de la salle, à côté du QR code.",
    warning: "Attention, il change régulièrement : vérifiez qu'il est toujours le même avant de valider.",
    sample: 'Exemple',
    sampleFrom: 'Depuis votre téléphone',
    close: 'Fermer ce message',
    errorPrefix: 'Le code',
    errorSuffix: 'est erroné ou expiré, veuillez réessayer.',
    themeToLight: 'Passer en thème clair',
    themeToDark: 'Passer en thème sombre',
    boxLabel: (i) => `Caractère ${i + 1} sur ${CODE_LENGTH}`,
  },
  en: {
    title: 'Control your meeting',
    subtitle: 'Enter the code shown on screen',
    button: 'Submit',
    hintTitle: 'Where to find the code?',
    hint: 'This 5-character code is shown on the room screen, next to the QR code.',
    warning: 'Note: it changes regularly — make sure it still matches before submitting.',
    sample: 'Example',
    sampleFrom: 'From your phone',
    close: 'Dismiss this message',
    errorPrefix: 'Code',
    errorSuffix: 'is invalid or expired, please try again.',
    themeToLight: 'Switch to light theme',
    themeToDark: 'Switch to dark theme',
    boxLabel: (i) => `Character ${i + 1} of ${CODE_LENGTH}`,
  },
};

// The code the proxy turned down, quoted back in the error message. The boxes
// are cleared rather than kept: a refused code is not worth correcting one
// character at a time, re-reading it from the room screen is the point.
let rejectedCode = '';

let lang = localStorage.getItem('lang') || 'fr';
if (!TEXTS[lang]) lang = 'fr';

// The banner stays until it is closed rather than fading on a timer: it names
// the code that was turned down, and the reader may need it while checking the
// room screen.
let dismissed = false;

let dark = localStorage.getItem('theme')
  ? localStorage.getItem('theme') === 'dark'
  : window.matchMedia('(prefers-color-scheme: dark)').matches;

const $ = (id) => document.getElementById(id);
const boxes = [];

// --- code entry ------------------------------------------------------------

function buildBoxes() {
  const wrap = $('code-boxes');
  for (let i = 0; i < CODE_LENGTH; i++) {
    const box = document.createElement('input');
    box.type = 'text';
    box.inputMode = 'text';
    box.autocomplete = 'off';
    box.autocapitalize = 'characters';
    box.spellcheck = false;
    box.maxLength = 1;
    box.addEventListener('input', () => onInput(i));
    box.addEventListener('keydown', (e) => onKeyDown(e, i));
    box.addEventListener('paste', onPaste);
    wrap.appendChild(box);
    boxes.push(box);
  }
}

function onInput(i) {
  const box = boxes[i];
  // The code is uppercase letters and digits; anything else is dropped rather
  // than rejected, so a stray keystroke does not interrupt the entry.
  box.value = box.value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(-1);
  if (box.value && i < CODE_LENGTH - 1) boxes[i + 1].focus();
  refresh();
}

function onKeyDown(e, i) {
  if (e.key === 'Backspace' && !boxes[i].value && i > 0) {
    boxes[i - 1].focus();
  } else if (e.key === 'ArrowLeft' && i > 0) {
    e.preventDefault();
    boxes[i - 1].focus();
  } else if (e.key === 'ArrowRight' && i < CODE_LENGTH - 1) {
    e.preventDefault();
    boxes[i + 1].focus();
  }
}

// A code copied from elsewhere arrives in one box: spread it across all of them.
function onPaste(e) {
  e.preventDefault();
  const text = (e.clipboardData || window.clipboardData).getData('text');
  setCode(text);
}

function setCode(value) {
  const chars = String(value).toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, CODE_LENGTH);
  boxes.forEach((box, i) => { box.value = chars[i] || ''; });
  refresh();
  const next = chars.length < CODE_LENGTH ? chars.length : CODE_LENGTH - 1;
  boxes[next].focus();
}

function code() {
  return boxes.map((b) => b.value).join('');
}

function refresh() {
  const complete = code().length === CODE_LENGTH;
  boxes.forEach((b) => b.classList.toggle('filled', !!b.value));
  $('btn').disabled = !complete;
}

// --- rendering -------------------------------------------------------------

function render() {
  const t = TEXTS[lang];

  document.documentElement.lang = lang;
  document.documentElement.dataset.theme = dark ? 'dark' : 'light';

  $('lang-fr').setAttribute('aria-checked', String(lang === 'fr'));
  $('lang-en').setAttribute('aria-checked', String(lang === 'en'));

  const toggle = $('theme-toggle');
  toggle.textContent = dark ? '☀' : '☾';
  toggle.setAttribute('aria-pressed', String(dark));
  toggle.setAttribute('aria-label', dark ? t.themeToLight : t.themeToDark);

  $('title').textContent = t.title;
  $('subtitle').textContent = t.subtitle;
  $('btn-label').textContent = t.button;
  $('hint-title').textContent = t.hintTitle;
  $('hint-text').textContent = t.hint;
  $('hint-warning').textContent = t.warning;
  $('sample-badge').textContent = t.sample;
  $('sample-from').textContent = t.sampleFrom;

  boxes.forEach((box, i) => box.setAttribute('aria-label', t.boxLabel(i)));

  // The rejected code is named in the message: on a screen where five boxes
  // now sit empty, "this code" alone would leave the reader wondering which.
  const banner = $('error-banner');
  banner.hidden = !rejectedCode || dismissed;
  if (rejectedCode) {
    const text = $('error-text');
    text.textContent = '';
    text.append(t.errorPrefix + ' ');
    const codeEl = document.createElement('b');
    codeEl.textContent = rejectedCode;
    text.append(codeEl, ' ' + t.errorSuffix);
    $('error-close').setAttribute('aria-label', t.close);
  }

  // The address the room screen shows under the code. Taken from where the
  // visitor already is, so the illustration matches their own deployment.
  $('sample-url').textContent = window.location.host;

  const link = $('doc-link');
  if (BRAND.docUrl) {
    link.href = BRAND.docUrl;
    link.textContent = lang === 'fr' ? BRAND.docLabelFr : BRAND.docLabelEn;
  } else {
    link.parentElement.hidden = true;
  }
}

function applyBrand() {
  $('brand-name').textContent = BRAND.name;
  $('brand-tagline').textContent = BRAND.tagline;
  if (BRAND.logo) {
    const logo = $('brand-logo');
    logo.src = BRAND.logo;
    logo.alt = BRAND.name;
  }
}

function setLang(value) {
  lang = value;
  localStorage.setItem('lang', value);
  render();
}

// --- startup ---------------------------------------------------------------

buildBoxes();
applyBrand();

$('lang-fr').addEventListener('click', () => setLang('fr'));
$('lang-en').addEventListener('click', () => setLang('en'));
// A click in the gaps between boxes lands on the strip itself; send it to the
// first box still waiting for a character.
$('code-boxes').addEventListener('mousedown', (e) => {
  if (e.target !== e.currentTarget) return;   // a box was clicked, leave it be
  e.preventDefault();
  const next = boxes.find((b) => !b.value) || boxes[CODE_LENGTH - 1];
  next.focus();
});

$('error-close').addEventListener('click', () => {
  dismissed = true;
  $('error-banner').hidden = true;
});

$('theme-toggle').addEventListener('click', () => {
  dark = !dark;
  localStorage.setItem('theme', dark ? 'dark' : 'light');
  render();
});

// The code is checked before going anywhere: the page asks the proxy, and
// only navigates once it knows the code is live. A refused one is answered
// here, without a round trip that would leave the address bar on a page the
// visitor is not looking at.
async function submit() {
  const value = code();
  if (value.length !== CODE_LENGTH) return;

  $('spinner').hidden = false;
  $('btn').disabled = true;
  rejectedCode = '';
  dismissed = false;
  render();

  let gwId = null;
  try {
    const res = await fetch('/pairing/resolve', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code: value }),
    });
    if (res.ok) gwId = (await res.json())?.data?.gw_id || null;
  } catch (e) {
    // Unreachable proxy reads the same as a refused code here: either way the
    // visitor has nothing to do but try again.
  }

  if (gwId) {
    // The spinner keeps running until the browser leaves the page.
    window.location.href = '/interact?gwId=' + encodeURIComponent(gwId);
    return;
  }

  rejectedCode = value;
  $('spinner').hidden = true;
  boxes.forEach((b) => { b.value = ''; });
  refresh();
  render();
  boxes[0].focus();
}

$('btn').addEventListener('click', submit);

// Coming back with the browser's Back button restores the page from its cache,
// spinner still turning and boxes still filled, without re-running any of this.
// pageshow fires on that restore too, which is where the entry is reset.
window.addEventListener('pageshow', (e) => {
  if (!e.persisted) return;
  $('spinner').hidden = true;
  rejectedCode = '';
  dismissed = false;
  boxes.forEach((b) => { b.value = ''; });
  refresh();
  render();
  boxes[0].focus();
});

// Enter anywhere in the strip submits, as a form would have.
$('code-boxes').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') { e.preventDefault(); submit(); }
});

render();
refresh();
boxes[0].focus();
