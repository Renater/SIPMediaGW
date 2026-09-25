/* Entities (Settings tab): the entities, the ordered rules that attach a
   calling endpoint to one, a probe that says which rule decides, and the
   reclassification of the history.

   Rules are read top to bottom and the last one that matches decides. The
   order is the rule, so it is shown as numbers and moved with arrows, and
   the probe answers "which one wins" before anyone reorders by guesswork.
   Who changed what is in the audit tab, with the account changes.

   The server enforces everything the dialogs check (literal prefix/suffix,
   no leading or trailing space, a description, no duplicate), and writes
   every change to the audit in the same statement. */

import { get, post, put, del, errorMessage } from '../api.js';
import { t, translate, onLanguageChange } from '../i18n.js';
import { esc, nf } from '../format.js';
import { closeDialogs, wireDialogs } from '../ui.js';

let units = [], rules = [], unassigned = 0;
let stopListening = null, mounted = false;
let editingUnit = null, editingRule = null, confirmAction = null;
const $ = id => document.getElementById(id);

const PENCIL = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 20h4l10.5-10.5a2.1 2.1 0 0 0-3-3L5 17v3z"/><path d="M13.5 6.5l3 3"/></svg>';
const TRASH = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/></svg>';
const UP = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 19V5M6 11l6-6 6 6"/></svg>';
const DOWN = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 5v14M6 13l6 6 6-6"/></svg>';

const unitLabel = code => (units.find(unit => unit.code === code) || {}).label || code;
const ruleText = rule => `${t().ouFields[rule.field] || rule.field} ${t().ouMatches[rule.match_type] || rule.match_type} ${t().quoted(rule.pattern)}`;

/* ------------------------------------------------------------ drawing */

function unitRow(unit) {
  return `<tr data-enabled="${unit.active ? 'true' : 'false'}">
    <td class="mono">${esc(unit.code)}</td>
    <td>${esc(unit.label)}</td>
    <td class="center num">${nf.format(unit.rules)}</td>
    <td class="center num">${nf.format(unit.calls)}</td>
    <td>${esc(unit.active ? t().ouActive : t().ouInactive)}</td>
    <td class="actions"><div>
      <button class="icon" data-action="edit-unit" data-code="${esc(unit.code)}" aria-label="${esc(t().ouEditUnit(unit.code))}" title="${esc(t().userEditShort)}">${PENCIL}</button>
    </div></td>
  </tr>`;
}

function ruleRow(rule, index) {
  const last = index === rules.length - 1;
  return `<tr data-enabled="${rule.active ? 'true' : 'false'}" data-rule="${esc(rule.id)}">
    <td class="center num">${esc(rule.id)}</td>
    <td>${esc(unitLabel(rule.org_unit_code))}</td>
    <td>${esc(t().ouFields[rule.field] || rule.field)}</td>
    <td>${esc(t().ouMatches[rule.match_type] || rule.match_type)}</td>
    <td class="mono">${esc(rule.pattern)}</td>
    <td>${esc(rule.description || '—')}</td>
    <td>${esc(rule.active ? t().ouActive : t().ouInactive)}</td>
    <td class="center num">${index + 1}</td>
    <td class="actions"><div>
      <button class="icon" data-action="up" data-id="${esc(rule.id)}" aria-label="${esc(t().ouUp)}" title="${esc(t().ouUp)}"${index === 0 ? ' disabled' : ''}>${UP}</button>
      <button class="icon" data-action="down" data-id="${esc(rule.id)}" aria-label="${esc(t().ouDown)}" title="${esc(t().ouDown)}"${last ? ' disabled' : ''}>${DOWN}</button>
      ${rule.match_type === 'regex' ? '' : `<button class="icon" data-action="edit-rule" data-id="${esc(rule.id)}" aria-label="${esc(t().ouEditRule(rule.id))}" title="${esc(t().userEditShort)}">${PENCIL}</button>`}
      <button class="icon" data-action="delete-rule" data-id="${esc(rule.id)}" aria-label="${esc(t().ouDeleteRule(rule.id))}" title="${esc(t().userDelete)}">${TRASH}</button>
    </div></td>
  </tr>`;
}

/* Centred columns carry numbers: the header sits over them. */
function head(id, columns, centred = []) {
  $(id).innerHTML = columns
    .map((column, i) => `<th${centred.includes(i) ? ' class="center"' : ''}>${esc(column)}</th>`).join('');
}

/* One function per table: each header list is checked against its own rows. */
function drawUnits() {
  head('ouUnitsHead', t().ouUnitCols, [2, 3]);
  $('ouUnits').innerHTML = units.length
    ? units.map(unitRow).join('')
    : `<tr><td class="msg" colspan="6">${esc(t().noData)}</td></tr>`;
}

function drawRules() {
  head('ouRulesHead', t().ouRuleCols, [0, 7]);
  $('ouRules').innerHTML = rules.length
    ? rules.map(ruleRow).join('')
    : `<tr><td class="msg" colspan="9">${esc(t().noData)}</td></tr>`;
}

function draw() {
  drawUnits();
  drawRules();
  $('ouUnassigned').textContent = t().ouUnassigned(unassigned);
}

async function load() {
  const data = await get('/api/org-units');
  if (!mounted) return;
  units = data.units || [];
  rules = data.rules || [];
  unassigned = data.unassigned || 0;
  draw();
}

function reload() {
  load().catch(error => {
    if (error.message !== 'unauthenticated' && mounted) $('ouMsg').textContent = errorMessage(error, t());
  });
}

/* The server's reasons, in the reader's language. */
function reason(status, detail) {
  if (status === 409 && /same rule/.test(detail)) return t().ouDuplicate;
  if (status === 409 && /code already exists/.test(detail)) return t().ouCodeExists;
  if (status === 409 && /changed meanwhile/.test(detail)) return t().ouStale;
  if (/start or end with a space/.test(detail)) return t().ouSpaces;
  if (/description is required/.test(detail)) return t().ouNeedDescription;
  if (/pattern is required/.test(detail)) return t().ouNeedPattern;
  if (/label is required/.test(detail)) return t().ouNeedLabel;
  if (/code:/.test(detail)) return t().ouBadCode;
  return t().requestFailed;
}

/* ------------------------------------------------------------ entities */

function fillSelects() {
  const states = `<option value="true">${esc(t().ouActive)}</option><option value="false">${esc(t().ouInactive)}</option>`;
  $('ouUnitActive').innerHTML = states;
  $('ouRuleActive').innerHTML = states;
  $('ouRuleField').innerHTML = ['uri', 'alias']
    .map(field => `<option value="${field}">${esc(t().ouFields[field])}</option>`).join('');
  $('ouRuleMatch').innerHTML = ['prefix', 'suffix']
    .map(match => `<option value="${match}">${esc(t().ouMatches[match])}</option>`).join('');
}

function openUnit(code) {
  const unit = units.find(row => row.code === code);
  editingUnit = unit ? unit.code : null;
  $('ouUnitTitle').textContent = unit ? t().ouEditUnit(unit.code) : t().ouUnitAdd;
  $('ouUnitCode').value = unit ? unit.code : '';
  $('ouUnitCode').disabled = !!unit;      // the code is what calls point at
  $('ouUnitLabel').value = unit ? unit.label : '';
  $('ouUnitActive').value = String(unit ? unit.active : true);
  $('ouUnitActive').disabled = !unit;
  $('ouUnitError').textContent = '';
  $('ouUnitDialog').showModal();
  (unit ? $('ouUnitLabel') : $('ouUnitCode')).focus();
}

async function submitUnit(event) {
  event.preventDefault();
  $('ouUnitSave').disabled = true;
  try {
    const answer = editingUnit
      ? await put(`/api/org-units/${encodeURIComponent(editingUnit)}`,
                  { label: $('ouUnitLabel').value, active: $('ouUnitActive').value === 'true' })
      : await post('/api/org-units', { code: $('ouUnitCode').value.trim(), label: $('ouUnitLabel').value });
    if (!answer.ok) { $('ouUnitError').textContent = reason(answer.status, answer.data.detail || ''); return; }
    $('ouUnitDialog').close();
    $('ouMsg').textContent = t().setSaved;
    reload();
  } finally {
    $('ouUnitSave').disabled = false;
  }
}

/* --------------------------------------------------------------- rules */

function openRule(id) {
  const rule = rules.find(row => String(row.id) === String(id));
  editingRule = rule ? rule.id : null;
  $('ouRuleTitle').textContent = rule ? t().ouEditRule(rule.id) : t().ouRuleAdd;
  $('ouRuleUnit').innerHTML = units
    .map(unit => `<option value="${esc(unit.code)}">${esc(unit.label)} (${esc(unit.code)})</option>`).join('');
  $('ouRuleField').value = rule ? rule.field : 'uri';
  $('ouRuleMatch').value = rule ? rule.match_type : 'prefix';
  $('ouRulePattern').value = rule ? rule.pattern : '';
  $('ouRuleUnit').value = rule ? rule.org_unit_code : (units[0] || {}).code || '';
  $('ouRuleActive').value = String(rule ? rule.active : true);
  $('ouRuleDescription').value = rule ? rule.description || '' : '';
  $('ouRuleError').textContent = '';
  $('ouRuleDialog').showModal();
  $('ouRulePattern').focus();
}

async function submitRule(event) {
  event.preventDefault();
  $('ouRuleSave').disabled = true;
  try {
    // Sent as typed: a space around a value is refused by the server with a
    // reason, never trimmed here into a rule nobody wrote.
    const body = {
      org_unit_code: $('ouRuleUnit').value, field: $('ouRuleField').value,
      match_type: $('ouRuleMatch').value, pattern: $('ouRulePattern').value,
      description: $('ouRuleDescription').value, active: $('ouRuleActive').value === 'true',
    };
    const answer = editingRule
      ? await put(`/api/org-unit-rules/${encodeURIComponent(editingRule)}`, body)
      : await post('/api/org-unit-rules', body);
    if (!answer.ok) { $('ouRuleError').textContent = reason(answer.status, answer.data.detail || ''); return; }
    $('ouRuleDialog').close();
    $('ouMsg').textContent = editingRule ? t().setSaved : t().ouRuleAdded;
    reload();
  } finally {
    $('ouRuleSave').disabled = false;
  }
}

async function move(id, step) {
  const ids = rules.map(rule => rule.id);
  const from = ids.findIndex(value => String(value) === String(id));
  const to = from + step;
  if (from < 0 || to < 0 || to >= ids.length) return;
  [ids[from], ids[to]] = [ids[to], ids[from]];
  const answer = await put('/api/org-unit-rules-order', { ids });
  $('ouMsg').textContent = answer.ok ? '' : reason(answer.status, answer.data.detail || '');
  reload();
}

/* -------------------------------------------------- confirmation dialog */

function confirm(text, button, danger, action) {
  confirmAction = action;
  $('ouConfirmText').textContent = text;
  $('ouConfirmButton').textContent = button;
  $('ouConfirmButton').className = danger ? 'danger' : 'primary';
  $('ouConfirmError').textContent = '';
  $('ouConfirmDialog').showModal();
  $('ouConfirmButton').focus();
}

async function submitConfirm(event) {
  event.preventDefault();
  if (!confirmAction) return;
  $('ouConfirmButton').disabled = true;
  try {
    const message = await confirmAction();
    if (message instanceof Error) { $('ouConfirmError').textContent = message.message; return; }
    $('ouConfirmDialog').close();
    $('ouMsg').textContent = message || '';
    reload();
  } finally {
    $('ouConfirmButton').disabled = false;
  }
}

function askDelete(id) {
  const index = rules.findIndex(rule => String(rule.id) === String(id));
  if (index < 0) return;
  const rule = rules[index];
  confirm(t().ouDeleteText(rule.id, index + 1, ruleText(rule), unitLabel(rule.org_unit_code)), t().userDelete, true, async () => {
    const answer = await del(`/api/org-unit-rules/${encodeURIComponent(rule.id)}`);
    return answer.ok ? t().ouRuleDeleted(rule.id) : new Error(reason(answer.status, answer.data.detail || ''));
  });
}

function askRecompute() {
  confirm(t().ouRecomputeText, t().ouRecompute, false, async () => {
    const answer = await post('/api/org-units/recompute', {});
    return answer.ok ? t().ouMoved(answer.data.rows_moved || 0) : new Error(reason(answer.status, answer.data.detail || ''));
  });
}

/* --------------------------------------------------------------- probe */

async function probe(event) {
  event.preventDefault();
  const answer = await post('/api/org-unit-rules/test', {
    uri: $('ouTestUri').value, alias: $('ouTestAlias').value,
  });
  if (!answer.ok) { $('ouTestResult').textContent = reason(answer.status, answer.data.detail || ''); return; }
  const winner = answer.data.winner;
  const others = (answer.data.matches || []).filter(rule => !winner || rule.id !== winner.id);
  $('ouTestResult').textContent = winner
    ? t().ouTestWinner(unitLabel(winner.org_unit_code), winner.id, ruleText(winner))
      + (others.length ? ' ' + t().ouTestOthers(others.map(rule => rule.id).join(', ')) : '')
    : t().ouTestNone;
}

/* -------------------------------------------------------------- wiring */

function applyLanguage() {
  if (!mounted || !$('ouUnits')) return;
  translate(document);
  fillSelects();
  draw();
}

export function mount() {
  mounted = true;
  applyLanguage();
  stopListening = onLanguageChange(applyLanguage);
  reload();

  $('ouUnitAdd').addEventListener('click', () => openUnit(null));
  $('ouRuleAdd').addEventListener('click', () => {
    if (!units.length) { $('ouMsg').textContent = t().ouNeedUnit; return; }
    openRule(null);
  });
  $('ouRecompute').addEventListener('click', askRecompute);
  $('ouUnitForm').addEventListener('submit', submitUnit);
  $('ouRuleForm').addEventListener('submit', submitRule);
  $('ouConfirmForm').addEventListener('submit', submitConfirm);
  $('ouTestForm').addEventListener('submit', probe);
  $('ouUnits').addEventListener('click', event => {
    const button = event.target.closest('[data-action="edit-unit"]');
    if (button) openUnit(button.dataset.code);
  });
  $('ouRules').addEventListener('click', event => {
    const button = event.target.closest('[data-action]');
    if (!button || button.disabled) return;
    const id = button.dataset.id;
    if (button.dataset.action === 'up') move(id, -1);
    if (button.dataset.action === 'down') move(id, 1);
    if (button.dataset.action === 'edit-rule') openRule(id);
    if (button.dataset.action === 'delete-rule') askDelete(id);
  });
  wireDialogs(document.getElementById('view'));
}

export function unmount() {
  mounted = false;
  closeDialogs(document.getElementById('view'));
  if (stopListening) stopListening();
  stopListening = null;
}
