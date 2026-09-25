/* Audit (Settings tab): every administrative change, accounts and entities
   in one list, newest first, each line with its type. The two sides keep
   their own tables; the server reads them together. */

import { get, errorMessage } from '../api.js';
import { t, translate, onLanguageChange } from '../i18n.js';
import { esc } from '../format.js';
import { createCalendar, openFromFields, keyOf, isoOf, shortDate, todayKey, addDays } from '../datepicker.js';

const TYPES = ['user', 'entity'];
const PAGE_SIZE = 50;
const DEBOUNCE_MS = 300;
let lines = [], total = 0, offset = 0, picked = [...TYPES];
let stopListening = null, mounted = false, requestId = 0, debounceTimer = null;
let range = null, calendar = null;
const $ = id => document.getElementById(id);

/* Whole days: an audit is read by day, not by hour. */
const PRESETS = {
  today: () => [todayKey(), todayKey()],
  last_7: () => [addDays(todayKey(), -6), todayKey()],
  last_30: () => [addDays(todayKey(), -29), todayKey()],
  month: () => { const n = new Date(); return [keyOf(new Date(n.getFullYear(), n.getMonth(), 1)), todayKey()]; },
  last_month: () => {
    const n = new Date();
    return [keyOf(new Date(n.getFullYear(), n.getMonth() - 1, 1)), keyOf(new Date(n.getFullYear(), n.getMonth(), 0))];
  },
  year: () => [keyOf(new Date(new Date().getFullYear(), 0, 1)), todayKey()],
};

function setRange(start, end, preset) {
  range = { start, end: end < start ? start : end };
  $('auditPreset').value = preset;
  $('auditFromValue').textContent = shortDate(range.start);
  $('auditToValue').textContent = shortDate(range.end);
  offset = 0;
  load();
}

const when = iso => {
  if (!iso) return '—';
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString();
};

/* What changed, in a line. An account line carries flags and names (never
   a password); an entity line carries the rule or the entity as it was
   before and after the change. */
function summary(line) {
  const detail = line.detail || {};
  if (line.type === 'user') {
    return Object.entries(detail)
      .map(([key, value]) => {
        const shown = value === true ? t().yes : value === false ? t().no
          : key === 'role' ? t().roles[value] || value : key === 'source' ? t().sources[value] || value : value;
        return `${t().auditUserFields[key] || key} : ${shown}`;
      })
      .join(' · ');
  }
  const shown = detail.after || detail.before || {};
  if (shown.pattern !== undefined) {
    return `${t().ouFields[shown.field] || shown.field} ${t().ouMatches[shown.match_type] || shown.match_type} ${t().quoted(shown.pattern)} → ${shown.org_unit_code || ''}`;
  }
  if (shown.label !== undefined) return `${shown.code} — ${shown.label}${shown.active === false ? ` (${t().ouInactive})` : ''}`;
  if (line.action === 'recompute') return t().ouMoved(detail.rows_moved || 0);
  if (line.action === 'rules_order') return t().ouReordered;
  return '';
}

/* "rule 12" is the rule's identifier, not its place in the list, which moves. */
function target(value) {
  const rule = /^rule (\d+)$/.exec(value || '');
  if (rule) return t().auditRuleTarget(rule[1]);
  return t().auditTargets[value] || value;
}

/* A neutral pill: the type is a category, not a state to colour. */
function rowHtml(line) {
  const actions = line.type === 'user' ? t().auditUserActions : t().ouActions;
  return `<tr>
    <td>${esc(when(line.at))}</td>
    <td><span class="pill free">${esc(t().auditTypes[line.type] || line.type)}</span></td>
    <td>${esc(line.actor)}</td>
    <td>${esc(actions[line.action] || line.action)}</td>
    <td>${esc(target(line.target))}</td>
    <td>${esc(summary(line))}</td>
  </tr>`;
}

function draw() {
  $('auditHead').innerHTML = t().auditCols.map(column => `<th>${esc(column)}</th>`).join('');
  $('auditShown').textContent = t().auditShown(total);
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  $('auditPage').textContent = t().callsPage(Math.floor(offset / PAGE_SIZE) + 1, pages);
  $('auditPrev').disabled = offset === 0;
  $('auditNext').disabled = offset + PAGE_SIZE >= total;
  $('auditRows').innerHTML = lines.length
    ? lines.map(rowHtml).join('')
    : `<tr><td class="msg" colspan="6">${esc(t().noData)}</td></tr>`;
}

function drawFilter() {
  $('auditTypeList').innerHTML = TYPES.map(type => `<label>
      <input type="checkbox" value="${esc(type)}"${picked.includes(type) ? ' checked' : ''}>
      <span>${esc(t().auditTypes[type])}</span></label>`).join('');
  const name = t().auditTypeName;
  $('auditTypeButton').textContent = picked.length === TYPES.length ? t().filterEvery(name)
    : picked.length === 0 ? t().filterNothing(name)
    : `${name} : ${t().auditTypes[picked[0]]}`;
}

async function load() {
  const id = ++requestId;
  if (!picked.length) { lines = []; total = 0; draw(); return; }
  const query = new URLSearchParams({
    types: picked.join(','), q: $('auditSearch').value.trim(),
    start: `${isoOf(range.start)}T00:00:00`, end: `${isoOf(range.end)}T23:59:59.999999`,
    limit: String(PAGE_SIZE), offset: String(offset),
  });
  try {
    const answer = await get(`/api/audit?${query}`);
    if (!mounted || id !== requestId) return;
    lines = answer.lines || [];
    total = answer.total || 0;
    draw();
  } catch (error) {
    if (error.message === 'unauthenticated' || !mounted || id !== requestId) return;
    $('auditRows').innerHTML = `<tr><td class="msg err" colspan="6">${esc(errorMessage(error, t()))}</td></tr>`;
  }
}

function pick(values) {
  picked = TYPES.filter(type => values.includes(type));
  offset = 0;
  drawFilter();
  load();
}

function closePanel(event) {
  const box = $('auditTypeFilter');
  if (box && !box.contains(event.target)) $('auditTypePanel').hidden = true;
}

function applyLanguage() {
  if (!mounted || !$('auditRows')) return;
  translate(document);
  $('auditSearch').placeholder = t().auditSearch;
  $('auditPrev').setAttribute('aria-label', t().pagerPrev);
  $('auditNext').setAttribute('aria-label', t().pagerNext);
  const selected = $('auditPreset').value;
  $('auditPreset').innerHTML = Object.keys(PRESETS)
    .map(key => `<option value="${key}">${esc(t().auditPresets[key])}</option>`).join('')
    + `<option value="custom">${esc(t().callPresets.custom)}</option>`;
  $('auditPreset').value = selected || 'last_30';
  calendar.refresh();
  drawFilter();
  draw();
}

export function mount() {
  mounted = true;
  offset = 0;
  calendar = createCalendar({
    panel: $('auditCalendar'), mode: 'range', max: todayKey(),
    onApply: ({ start, end }) => setRange(start, end, 'custom'),
  });
  const [start, end] = PRESETS.last_30();
  range = { start, end };
  applyLanguage();
  stopListening = onLanguageChange(applyLanguage);
  setRange(start, end, 'last_30');
  $('auditPreset').addEventListener('change', event => {
    const name = event.target.value;
    if (PRESETS[name]) setRange(...PRESETS[name](), name);
    else calendar.open({ start: range.start, end: range.end, picking: 'start', from: $('auditFrom') });
  });
  openFromFields(calendar, () => range, [[$('auditFrom'), 'start'], [$('auditTo'), 'end']]);
  // Searched as typed, a moment after the last key: who acted, or on whom.
  $('auditSearch').addEventListener('input', () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => { offset = 0; load(); }, DEBOUNCE_MS);
  });
  $('auditPrev').addEventListener('click', () => { offset = Math.max(0, offset - PAGE_SIZE); load(); });
  $('auditNext').addEventListener('click', () => {
    if (offset + PAGE_SIZE < total) { offset += PAGE_SIZE; load(); }
  });
  $('auditTypeButton').addEventListener('click', () => {
    $('auditTypePanel').hidden = !$('auditTypePanel').hidden;
  });
  $('auditTypePanel').addEventListener('change', event => {
    if (event.target.type !== 'checkbox') return;
    pick([...$('auditTypePanel').querySelectorAll('input:checked')].map(box => box.value));
  });
  for (const button of $('auditTypePanel').querySelectorAll('[data-pick]')) {
    button.addEventListener('click', () => pick(button.dataset.pick === 'all' ? [...TYPES] : []));
  }
  document.addEventListener('click', closePanel);
}

export function unmount() {
  mounted = false;
  clearTimeout(debounceTimer);
  if (calendar) calendar.destroy();
  calendar = null;
  document.removeEventListener('click', closePanel);
  if (stopListening) stopListening();
  stopListening = null;
}
