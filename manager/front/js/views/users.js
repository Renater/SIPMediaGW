/* Users (Settings tab): the account list, and three dialogs — add, edit,
   delete. The dialogs are native <dialog>: focus stays inside, Escape closes,
   the backdrop is drawn by the browser.

   What the list shows is what the server says; every change reloads it. The
   server also enforces every rule the dialogs apply (e-mail as username,
   password length, last administrator, own account), so a stale page cannot
   do what a fresh one refuses. */

import { get, post, put, del, errorMessage } from '../api.js';
import { t, translate, onLanguageChange } from '../i18n.js';
import { esc } from '../format.js';
import { closeDialogs, wireDialogs } from '../ui.js';

let accounts = [], stopListening = null, mounted = false;
let context = { user: '', minLength: 11 };
let editing = null;      // the username open in the edit dialog
const $ = id => document.getElementById(id);

/* ------------------------------------------------------------ rendering */

const when = iso => {
  if (!iso) return '—';
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString();
};

const fullName = row => [row.first_name, row.last_name].filter(Boolean).join(' ');

function stateTag(row) {
  if (!row.enabled) return `<span class="tag bad">${esc(t().userDisabled)}</span>`;
  if (row.must_change_password) return `<span class="tag warn">${esc(t().userMustChange)}</span>`;
  return `<span class="tag good">${esc(t().userActive)}</span>`;
}

/* One row. Kept out of draw() so that the colspan of the empty-list row sits
   in a plain assignment the static test can read. */
function rowHtml(row) {
  const self = row.username === context.user;
  return `<tr data-enabled="${row.enabled ? 'true' : 'false'}">
    <td>${esc(row.username)}${self ? ` <span class="dim">(${esc(t().userYou)})</span>` : ''}</td>
    <td>${esc(fullName(row) || '—')}</td>
    <td>${esc(t().roles[row.role] || row.role)}</td>
    <td>${esc(t().sources[row.source] || row.source)}</td>
    <td class="center">${stateTag(row)}</td>
    <td>${esc(when(row.last_login_at))}</td>
    <td class="actions">
      <button class="icon" data-action="edit" data-user="${esc(row.username)}" aria-label="${esc(t().userEdit(row.username))}" title="${esc(t().userEditShort)}">${PENCIL}</button>
      ${self ? '' : `<button class="icon" data-action="delete" data-user="${esc(row.username)}" aria-label="${esc(t().userDeleteAria(row.username))}" title="${esc(t().userDelete)}">${TRASH}</button>`}
    </td>
  </tr>`;
}

function draw() {
  $('usersHead').innerHTML = t().userCols.map((c, i) => `<th${i === 4 ? ' class="center"' : ''}>${esc(c)}</th>`).join('');
  $('users').innerHTML = accounts.length
    ? accounts.map(rowHtml).join('')
    : `<tr><td class="msg" colspan="7">${esc(t().noData)}</td></tr>`;
}

const PENCIL = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h4l10.5-10.5a2.1 2.1 0 0 0-3-3L5 17v3z"/><path d="M13.5 6.5l3 3"/></svg>';
const TRASH = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/></svg>';

async function load() {
  accounts = await get('/api/users');
  if (mounted) draw();
}

function reload() {
  load().catch(error => {
    if (error.message !== 'unauthenticated') $('userMsg').textContent = errorMessage(error, t());
  });
}

/* The server's reasons, in the reader's language where a person meets them. */
function userMessage(status, detail) {
  if (status === 409 && /last administrator/.test(detail)) return t().userLastAdmin;
  if (status === 409 && /already exists/.test(detail)) return t().userExists;
  if (status === 409 && /own role|itself/.test(detail)) return t().userSelf;
  if (/at least (\d+)/.test(detail)) return t().pwdTooShort(Number(/at least (\d+)/.exec(detail)[1]));
  if (/differ from the username/.test(detail)) return t().pwdIsUsername;
  if (/default password/.test(detail)) return t().pwdIsDefault;
  if (/e-mail/.test(detail)) return t().userBadEmail;
  if (/first name|last name/.test(detail)) return t().userNeedName;
  return t().requestFailed;
}

/* ------------------------------------------------------------- dialogs */

function fillSelects() {
  const roles = ['operator', 'admin'].map(role => `<option value="${role}">${esc(t().roles[role])}</option>`).join('');
  $('newUserRole').innerHTML = roles;
  $('editUserRole').innerHTML = roles;
  // ProConnect is announced, not offered: the accounts arrive with the SSO.
  $('newUserSource').innerHTML = `<option value="local">${esc(t().sources.local)}</option>`
    + `<option value="proconnect" disabled>${esc(t().sources.proconnect)} — ${esc(t().userSoon)}</option>`;
  $('editUserEnabled').innerHTML = `<option value="true">${esc(t().userActive)}</option>`
    + `<option value="false">${esc(t().userDisabled)}</option>`;
}

function openCreate() {
  $('userCreateForm').reset();
  $('userCreateError').textContent = '';
  $('userCreateRule').textContent = t().pwdRule(context.minLength);
  $('userCreateDialog').showModal();
  $('newUserName').focus();
}

async function submitCreate(event) {
  event.preventDefault();
  $('userCreateError').textContent = '';
  $('userCreateButton').disabled = true;
  try {
    const { ok, status, data } = await post('/api/users', {
      username: $('newUserName').value.trim(), first_name: $('newUserFirst').value.trim(),
      last_name: $('newUserLast').value.trim(), role: $('newUserRole').value,
      source: $('newUserSource').value, password: $('newUserPassword').value,
    });
    if (!ok) { $('userCreateError').textContent = userMessage(status, data.detail || ''); return; }
    $('userCreateDialog').close();
    $('userMsg').textContent = t().userCreated(data.username);
    reload();
  } finally {
    $('userCreateButton').disabled = false;
  }
}

function openEdit(name) {
  const row = accounts.find(account => account.username === name);
  if (!row) return;
  editing = name;
  const self = name === context.user;
  $('userEditTitle').textContent = t().userEditTitle(name);
  $('editUserFirst').value = row.first_name || '';
  $('editUserLast').value = row.last_name || '';
  $('editUserRole').value = row.role;
  $('editUserEnabled').value = String(row.enabled);
  // Own role and own state are not for this dialog: another administrator,
  // or the server tool, does that. The fields say so rather than fail later.
  $('editUserRole').disabled = self;
  $('editUserEnabled').disabled = self;
  $('editUserHint').textContent = self ? t().userSelfHint : '';
  $('editUserResetField').hidden = row.source !== 'local';
  $('editUserPassword').value = '';
  $('userEditError').textContent = '';
  $('userEditDialog').showModal();
  $('editUserFirst').focus();
}

async function submitEdit(event) {
  event.preventDefault();
  const name = editing;
  const row = accounts.find(account => account.username === name);
  if (!row) return;
  $('userEditError').textContent = '';
  $('userEditButton').disabled = true;
  try {
    const patch = {};
    // Both names travel together: the server wants a complete name, and the
    // bootstrap admin starts with none.
    const first = $('editUserFirst').value.trim(), last = $('editUserLast').value.trim();
    if (first !== (row.first_name || '') || last !== (row.last_name || '')) {
      patch.first_name = first;
      patch.last_name = last;
    }
    if (!$('editUserRole').disabled && $('editUserRole').value !== row.role) patch.role = $('editUserRole').value;
    if (!$('editUserEnabled').disabled && $('editUserEnabled').value !== String(row.enabled)) {
      patch.enabled = $('editUserEnabled').value === 'true';
    }
    if (Object.keys(patch).length) {
      const { ok, status, data } = await put(`/api/users/${encodeURIComponent(name)}`, patch);
      if (!ok) { $('userEditError').textContent = userMessage(status, data.detail || ''); return; }
    }
    const password = $('editUserPassword').value;
    if (password) {
      const { ok, status, data } = await post(`/api/users/${encodeURIComponent(name)}/password`, { password });
      if (!ok) { $('userEditError').textContent = userMessage(status, data.detail || ''); reload(); return; }
    }
    $('userEditDialog').close();
    $('userMsg').textContent = password ? t().userResetDone(name) : t().setSaved;
    reload();
  } finally {
    $('userEditButton').disabled = false;
  }
}

function openDelete(name) {
  editing = name;
  $('userDeleteText').textContent = t().userDeleteText(name);
  $('userDeleteError').textContent = '';
  $('userDeleteDialog').showModal();
  $('userDeleteButton').focus();
}

async function submitDelete(event) {
  event.preventDefault();
  const name = editing;
  $('userDeleteButton').disabled = true;
  try {
    const { ok, status, data } = await del(`/api/users/${encodeURIComponent(name)}`);
    if (!ok) { $('userDeleteError').textContent = userMessage(status, data.detail || ''); return; }
    $('userDeleteDialog').close();
    $('userMsg').textContent = t().userDeleted(name);
    reload();
  } finally {
    $('userDeleteButton').disabled = false;
  }
}

/* -------------------------------------------------------------- wiring */

function applyLanguage() {
  if (!mounted || !$('users')) return;
  translate(document);
  fillSelects();
  draw();
}

export function mount(appContext = {}) {
  mounted = true;
  context = { user: appContext.user || '', minLength: appContext.minLength || 11 };
  applyLanguage();
  stopListening = onLanguageChange(applyLanguage);
  reload();

  $('userAdd').addEventListener('click', openCreate);
  $('userCreateForm').addEventListener('submit', submitCreate);
  $('userEditForm').addEventListener('submit', submitEdit);
  $('userDeleteForm').addEventListener('submit', submitDelete);
  $('users').addEventListener('click', event => {
    const button = event.target.closest('[data-action]');
    if (!button) return;
    if (button.dataset.action === 'edit') openEdit(button.dataset.user);
    if (button.dataset.action === 'delete') openDelete(button.dataset.user);
  });
  wireDialogs(document.getElementById('view'));
}

export function unmount() {
  mounted = false;
  closeDialogs(document.getElementById('view'));
  if (stopListening) stopListening();
  stopListening = null;
}
