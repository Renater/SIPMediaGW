/* Application bootstrap: session, navigation and view loading.
   Views are HTML fragments under front/views/ paired with a module under
   front/js/views/; main.js knows nothing about their contents. */

import { get, post, html, onUnauthenticated, onPasswordRequired } from './api.js';
import { t, translate, setLanguage, initialLanguage, onLanguageChange } from './i18n.js';
import { esc, refreshNumberFormat } from './format.js';
import { wirePasswordForm } from './password.js';

const VIEWS = {
  supervision: { template: '/static/views/supervision.html', module: './views/supervision.js' },
  report: { template: '/static/views/report.html', module: './views/report.js' },
  calls: { template: '/static/views/calls.html', module: './views/calls.js' },
  quality: { template: '/static/views/quality.html', module: './views/quality.js' },
  capacity: { template: '/static/views/capacity.html', module: './views/capacity.js' },
  account: { template: '/static/views/account.html', module: './views/account.js' },
  users: { template: '/static/views/users.html', module: './views/users.js' },
  orgunits: { template: '/static/views/orgunits.html', module: './views/orgunits.js' },
  audit: { template: '/static/views/audit.html', module: './views/audit.js' },
};
const DEFAULT_VIEW = 'supervision';

const context = { interactUrl: '', role: 'operator', user: '', source: 'local', minLength: 11 };
let currentView = null, currentModule = null;

const $ = id => document.getElementById(id);

let switching = false;

async function showView(name) {
  // A second click while a view is still loading is ignored rather than
  // racing two imports against the same container.
  if (!VIEWS[name] || name === currentView || switching) return;
  if (['users', 'orgunits', 'audit'].includes(name) && context.role !== 'admin') return showView(DEFAULT_VIEW);
  switching = true;
  probeHealth();
  try {
    if (currentModule && currentModule.unmount) currentModule.unmount();
    currentModule = null;
    const view = VIEWS[name];
    $('view').innerHTML = await html(view.template);
    translate($('view'));
    currentModule = await import(view.module);
    currentView = name;
    // Capacity has no entry of its own: it is a tab of the report, so the
    // report's menu entry stays lit for both.
    for (const button of document.querySelectorAll('.nav[data-view]')) {
      const on = button.dataset.view === name
              || (button.dataset.view === 'report' && (name === 'capacity' || name === 'quality'))
              || (button.dataset.view === 'users' && (name === 'orgunits' || name === 'audit'));
      button.classList.toggle('on', on);
      button.setAttribute('aria-current', on ? 'page' : 'false');
    }
    window.location.hash = name;
  } catch (error) {
    // Nothing is mounted now; keeping the old name made the guard above
    // refuse to reopen this very view until another one was clicked.
    currentView = null;
    if (error.message !== 'unauthenticated') {
      $('view').innerHTML = `<div class="msg err">${esc(error.message)}</div>`;
    }
  } finally {
    switching = false;
  }
  // Data loading runs outside the lock: a slow API must never freeze the menu.
  // mount() may be synchronous, so normalise before attaching a handler.
  if (currentModule && currentView === name) {
    // mount() may be synchronous and may throw: wrap the call itself, not
    // only the promise it returns.
    Promise.resolve().then(() => currentModule.mount(context)).catch(error => {
      if (error.message !== 'unauthenticated') console.error('mount failed', error);
    });
  }
}

/* The database going away is otherwise a 503 on whichever panel is opened
   next, while the park view — which reads the proxy — stays live and
   reassuring. /health is the container healthcheck read from the browser;
   the banner stays up while it answers anything but 200. */
const HEALTH_EVERY_MS = 30000;
let healthTimer = null;

let health = 'ok';   // 'ok' | 'database' | 'manager'

function renderBanner() {
  const banner = $('dbBanner');
  banner.hidden = health === 'ok';
  banner.textContent = health === 'database' ? t().dbDown : health === 'manager' ? t().managerDown : '';
}

async function probeHealth() {
  try {
    const response = await fetch('/health', { cache: 'no-store' });
    // 503 is the probe's own answer (database away); anything else that
    // is not 200 — a 502 from a proxy, a 500 — is the Manager itself.
    health = response.ok ? 'ok' : response.status === 503 ? 'database' : 'manager';
  } catch {
    // fetch rejects: nothing answered at all (server rebooting, container down).
    health = 'manager';
  }
  renderBanner();
}

function startHealthProbe() {
  stopHealthProbe();
  probeHealth();
  healthTimer = setInterval(probeHealth, HEALTH_EVERY_MS);
}

function stopHealthProbe() {
  if (healthTimer) clearInterval(healthTimer);
  healthTimer = null;
}

function showApp(fresh = false) {
  $('loginView').hidden = true;
  $('app').hidden = false;
  // Settings is where the rate is written: an operator has no business
  // there, and the route would answer 403 anyway.
  document.querySelector('.nav[data-view="users"]').hidden = context.role !== 'admin';
  startHealthProbe();
  // A sign-in lands on Supervision; a reload (F5) stays where it was.
  const requested = fresh ? '' : window.location.hash.slice(1);
  showView(VIEWS[requested] ? requested : DEFAULT_VIEW);
}

function showLogin() {
  if (currentModule && currentModule.unmount) currentModule.unmount();
  currentModule = null;
  currentView = null;
  stopHealthProbe();
  $('app').hidden = true;
  $('loginView').hidden = false;
  $('passwordCard').hidden = true;
  $('loginCard').hidden = false;
  // The first field, not the password: the name is typed first.
  $('username').focus();
}
onUnauthenticated(showLogin);

/* The account must change its password before anything else: first sign-in
   with the initial password, or a reset by an administrator. The server
   refuses every other route with 403 until it is done. */
function showPasswordRequired() {
  $('pwdUser').value = context.user;
  if (currentModule && currentModule.unmount) currentModule.unmount();
  currentModule = null;
  currentView = null;
  stopHealthProbe();
  $('app').hidden = true;
  $('loginView').hidden = false;
  $('loginCard').hidden = true;
  $('passwordCard').hidden = false;
  $('pwdRequiredRule').textContent = t().pwdRequiredSub(context.minLength);
  $('pwdError').textContent = '';
  // Same convention as the sign-in card: the visible name is the placeholder.
  $('pwdCurrent').placeholder = t().pwdCurrent;
  $('pwdNext').placeholder = t().pwdNew;
  $('pwdConfirm').placeholder = t().pwdConfirm;
  $('pwdCurrent').focus();
}
onPasswordRequired(showPasswordRequired);
wirePasswordForm(
  { form: 'passwordForm', current: 'pwdCurrent', next: 'pwdNext', confirm: 'pwdConfirm',
    error: 'pwdError', button: 'pwdButton' },
  context,
  () => showApp(true));
$('pwdBack').addEventListener('click', async () => {
  await post('/auth/logout');
  showLogin();
});

function takeSession(session, fresh = false) {
  context.role = session.role || 'operator';
  context.user = session.user || '';
  context.source = session.source || 'local';
  context.minLength = session.password_min_length || 11;
  return session.must_change_password ? showPasswordRequired() : showApp(fresh);
}

async function login() {
  $('loginError').textContent = '';
  const { ok, status, data } = await post('/auth/login',
    { username: $('username').value.trim(), password: $('password').value });
  if (ok) {
    $('password').value = '';
    return takeSession(data, true);
  }
  // By status, not by server text: the API answers in English and the
  // throttle message is the one an operator is most likely to read.
  $('loginError').textContent = status === 429 ? t().loginThrottled : t().loginError;
}

/* ------------------------------------------------------------ wiring */

// A real form: the browser stops warning about a stray password field, and
// Enter submits without a key handler.
$('loginForm').addEventListener('submit', event => {
  event.preventDefault();
  login();
});
// Signing out is asked first: a click on the last entry of the menu, meant
// for "My account" just above, used to end the session outright.
$('logout').addEventListener('click', () => {
  const dialog = $('logoutDialog');
  dialog.returnValue = '';
  dialog.showModal();
  $('logoutConfirm').focus();
});
for (const button of $('logoutDialog').querySelectorAll('[data-close]')) {
  button.addEventListener('click', () => $('logoutDialog').close(''));
}
$('logoutDialog').addEventListener('close', async () => {
  if ($('logoutDialog').returnValue !== 'logout') return;
  await post('/auth/logout');
  showLogin();
});
for (const button of document.querySelectorAll('.nav[data-view]')) {
  button.addEventListener('click', () => showView(button.dataset.view));
}
// Sub-tabs live inside the templates, so the handler is delegated: the buttons
// do not exist when this runs.
$('view').addEventListener('click', event => {
  const tab = event.target.closest('[data-subview]');
  if (tab) showView(tab.dataset.subview);
});
// showView() writes the hash, so Back and Forward move it: follow them. A hash
// set by showView itself names the current view and is ignored by the guard.
window.addEventListener('hashchange', () => {
  const name = window.location.hash.slice(1);
  if (VIEWS[name] && !$('app').hidden) showView(name);
});
for (const button of document.querySelectorAll('.lang button')) {
  button.addEventListener('click', () => setLanguage(button.dataset.lang));
}
onLanguageChange(() => {
  refreshNumberFormat();
  renderBanner();
  $('password').placeholder = t().passwordPlaceholder;
  $('username').placeholder = t().usernamePlaceholder;
});

setLanguage(initialLanguage());

/* The service's name, tagline, logo and tab icon, as the deployment sets them
   (MANAGER_BRAND_*). Written as text and URLs: nothing from the configuration
   becomes markup. */
function applyBrand(brand) {
  const name = (brand && brand.name) || 'SIP Media Gateway Manager';
  document.title = name;
  for (const element of document.querySelectorAll('[data-brand="name"]')) element.textContent = name;
  for (const element of document.querySelectorAll('[data-brand="tagline"]')) {
    element.textContent = (brand && brand.tagline) || '';
    element.hidden = !element.textContent;
  }
  for (const logo of document.querySelectorAll('[data-brand="logo"]')) {
    if (brand && brand.logo) { logo.src = brand.logo; logo.alt = name; logo.hidden = false; } else logo.hidden = true;
  }
  if (brand && brand.favicon) $('favicon').href = brand.favicon;
}

get('/api/me')
  .then(session => {
    applyBrand(session.brand);
    context.interactUrl = session.interact_url || '';
    return session.authenticated ? takeSession(session) : showLogin();
  })
  .catch(showLogin);
