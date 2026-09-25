/* Call log: an explicit window, searchable, paginated, with a detail drawer.

   A busy day holds several hundred calls, so the window carries an hour of
   day and the table shows one page at a time. Presets fill the dates at once;
   a date picked in the calendar or an hour changed switches the preset to
   "custom" and keeps everything else, so what is on screen always matches
   what was queried. */

import { get, errorMessage } from '../api.js';
import { t, translate, onLanguageChange } from '../i18n.js';
import { esc, nf, norm, dash, copyable } from '../format.js';
import { enableCopy } from '../ui.js';
import { platformCell, attachIconFallback } from '../platforms.js';
import { createCalendar, openFromFields, keyOf, isoOf, shortDate, todayKey } from '../datepicker.js';
import { timeLines, attachHover, themeColor } from '../charts.js';
import { takeJournalFilter } from '../journal-link.js';

const DEBOUNCE_MS = 300;
const PAGE_SIZE = 50;

let stopListening = null, debounceTimer = null, requestId = 0, mounted = false;
let offset = 0, total = 0;
/* Exact filters. Outcomes and video states are ticked in two lists, as the
   units are in the report: all ticked filters nothing, none ticked shows
   nothing. A link from the Quality view ticks its own value and may add a
   close reason, shown as a chip since a raw reason reads badly in a list.
   The search box still applies on top. */
let reason = null;
const picked = { outcome: null, video: null };   // arrays; filled on mount

const $ = id => document.getElementById(id);

/* ------------------------------------------------------- date helpers */

const pad = n => String(n).padStart(2, '0');

const startOfDay = date => new Date(date.getFullYear(), date.getMonth(), date.getDate(), 0, 0);
const endOfDay = date => new Date(date.getFullYear(), date.getMonth(), date.getDate(), 23, 59);
const addDays = (date, days) => new Date(date.getFullYear(), date.getMonth(), date.getDate() + days);

/* Monday-based weeks, as elsewhere in the report. */
function startOfWeek(date) {
  const day = (date.getDay() + 6) % 7;
  return startOfDay(addDays(date, -day));
}

const PRESETS = {
  today: () => { const n = new Date(); return [startOfDay(n), endOfDay(n)]; },
  yesterday: () => { const d = addDays(new Date(), -1); return [startOfDay(d), endOfDay(d)]; },
  week: () => { const n = new Date(); return [startOfWeek(n), endOfDay(n)]; },
  last_week: () => {
    const start = addDays(startOfWeek(new Date()), -7);
    return [start, endOfDay(addDays(start, 6))];
  },
  month: () => {
    const n = new Date();
    return [new Date(n.getFullYear(), n.getMonth(), 1, 0, 0), endOfDay(n)];
  },
  last_month: () => {
    const n = new Date();
    const start = new Date(n.getFullYear(), n.getMonth() - 1, 1, 0, 0);
    return [start, endOfDay(new Date(n.getFullYear(), n.getMonth(), 0))];
  },
  last_7: () => [startOfDay(addDays(new Date(), -6)), endOfDay(new Date())],
  last_30: () => [startOfDay(addDays(new Date(), -29)), endOfDay(new Date())],
};

/* The window: two days and two whole hours, the end hour included ("to 16"
   runs to 16:59:59). With a hundred simultaneous calls at most an hour is a
   few pages, and the search box finds one call among them; minutes added a
   choice and no answer, since the window selects calls by their start. */
let range = null, calendar = null;

function presetRange(name) {
  const [start, end] = PRESETS[name]();
  return { start: keyOf(start), end: keyOf(end), from: 0, to: 23 };
}

/* The end follows the start: the window can never be reversed, and the
   server's "end is before start" is unreachable from the page. */
function normalise(next) {
  const out = { ...next };
  if (out.end < out.start) out.end = out.start;
  if (out.end === out.start && out.to < out.from) out.to = out.from;
  return out;
}

function hourOptions(select, selected, floor, label) {
  select.innerHTML = Array.from({ length: 24 }, (_, hour) =>
    `<option value="${hour}"${hour < floor ? ' disabled' : ''}>${esc(label(hour))}</option>`).join('');
  select.value = String(selected);
}

function drawRange() {
  $('callFromValue').textContent = shortDate(range.start);
  $('callToValue').textContent = shortDate(range.end);
  hourOptions($('callFromHour'), range.from, 0, t().hourFrom);
  // Same day: an end hour before the start hour is not offered at all.
  hourOptions($('callToHour'), range.to, range.start === range.end ? range.from : 0, t().hourTo);
}

function setRange(next, preset) {
  range = normalise(next);
  $('callPreset').value = preset;
  drawRange();
  reload();
}

/* --------------------------------------------------------- rendering */

/* source_name is filled from the call URL and is often empty; the macro also
   sends "<len>-<room><name>" as the SIP display name, so the endpoint name can
   be recovered from it rather than showing nothing. */
function displayName(row) {
  const direct = norm(row.source_name);
  if (direct) return direct;
  const encoded = norm(row.peer_display_name);
  if (!encoded) return null;
  const match = /^(\d+)-(.*)$/s.exec(encoded);
  if (!match) return encoded;
  const length = Number(match[1]);
  const rest = match[2];
  return rest.length > length ? rest.slice(length) : encoded;
}

function duration(seconds) {
  const value = Number(seconds) || 0;
  return `${pad(Math.floor(value / 3600))}:${pad(Math.floor(value % 3600 / 60))}:${pad(value % 60)}`;
}

function when(iso) {
  if (!iso) return dash;
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? dash : esc(date.toLocaleString());
}

const outcomeClass = outcome =>
  outcome === 'completed' ? 'call'
    : (outcome === 'failed' || outcome === 'not_established' ? 'other' : 'ivr');

const cellOrDash = value => norm(value) == null ? dash : esc(value);

/* The picture received, from the samples. Unknown shows nothing: a dash
   says "not measured" better than a word would, in a column of words. */
/* No picture is red too: on the lab it was video arriving that could not be
   decoded (1 784 packets, 3 frames, 36 key-frame requests in 29 s), not a
   camera turned off. */
const VIDEO_CLASS = { ok: 'good', stalled: 'bad', oneway: 'warn', no_picture: 'bad' };
const VIDEO_FILTERS = ['ok', 'stalled', 'no_picture', 'oneway', 'unknown'];
const OUTCOME_FILTERS = ['completed', 'ivr_only', 'failed', 'not_established'];
const videoCell = state => VIDEO_CLASS[state]
  ? `<span class="tag ${VIDEO_CLASS[state]}">${esc(t().videoStates[state])}</span>` : dash;

const COLUMNS = 10;

function render(rows) {
  $('callShown').textContent = t().callsShown(total);
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const page = Math.floor(offset / PAGE_SIZE) + 1;
  $('callPage').textContent = t().callsPage(page, pages);
  $('callPrev').disabled = offset === 0;
  $('callNext').disabled = offset + PAGE_SIZE >= total;

  if (!rows.length) {
    // nosemgrep: mgr-innerhtml-unescaped -- every value below goes through esc() (checked with poisoned data, tests/e2e/escaping.mjs)
    $('callRows').innerHTML = `<tr><td colspan="${COLUMNS}" class="msg">${esc(t().noCalls)}</td></tr>`;
    return;
  }
  // nosemgrep: mgr-innerhtml-unescaped -- every value below goes through esc() (checked with poisoned data, tests/e2e/escaping.mjs)
  $('callRows').innerHTML = rows.map(row => `<tr class="selectable" data-id="${esc(row.id)}">
    <td>${when(row.call_start)}</td>
    <td><span class="pill ${outcomeClass(row.outcome)}">${esc(t().outcomes[row.outcome] || row.outcome)}</span></td>
    <td>${copyable(displayName(row))}</td>
    <td>${copyable(norm(row.source_uri) || norm(row.source_number), 'mono')}</td>
    <td>${copyable(norm(row.room), 'mono')}</td>
    <td>${platformCell(row.platform, dash)}</td>
    <td>${cellOrDash(row.org_unit)}</td>
    <td class="num">${duration(row.duration_s)}</td>
    <td>${cellOrDash(row.terminal)}</td>
    <td>${videoCell(row.video_state)}</td>
  </tr>`).join('');
  attachIconFallback($('callRows'));
}

/* ------------------------------------------------------------- drawer */

function detailRows(call) {
  const labels = t().detailLabels;
  const entries = [
    ['call_id', norm(call.call_id)],
    ['outcome', t().outcomes[call.outcome] || call.outcome],
    ['call_start', call.call_start ? new Date(call.call_start).toLocaleString() : null],
    ['call_end', call.call_end ? new Date(call.call_end).toLocaleString() : null],
    ['duration_s', duration(call.duration_s)],
    ['occupancy_s', duration(call.occupancy_s)],
    ['close_reason', norm(call.close_reason)],
    ['last_event_type', norm(call.last_event_type)],
    ['source_name', displayName(call)],
    ['source_uri', norm(call.source_uri)],
    ['source_domain', norm(call.source_domain)],
    ['org_unit', norm(call.org_unit)],
    ['destination_uri', norm(call.destination_uri)],
    ['destination_domain', norm(call.destination_domain)],
    ['platform', norm(call.platform)],
    ['room', norm(call.room)],
    ['main_app', norm(call.main_app)],
    ['gw_alias', norm(call.gw_alias)],
    ['gw_host', norm(call.gw_host)],
    ['received_at', call.received_at ? new Date(call.received_at).toLocaleString() : null],
  ];
  return entries.map(([key, value]) =>
    `<tr><th>${esc(labels[key] || key)}</th><td>${value == null ? dash : copyable(String(value))}</td></tr>`).join('');
}

/* Terminal, negotiated media, code version, picture received: what the
   gateway pushes since SIPMediaGW #101, #102 and #105. A call pushed before
   has none of it, and the blocks are left out rather than filled with dashes. */
function block(title, entries) {
  const shown = entries.filter(([, value]) => value != null && value !== '');
  if (!shown.length) return '';
  return `<h3>${esc(title)}</h3><table class="detail"><tbody>${shown.map(([label, value]) =>
    `<tr><th>${esc(label)}</th><td>${copyable(String(value))}</td></tr>`).join('')}</tbody></table>`;
}

function directions(media) {
  if (!media) return null;
  return ['audio', 'video'].filter(key => media[key]).map(key => `${key} ${media[key]}`).join(' · ') || null;
}

function mediaDetails(call) {
  const l = t().mediaLabels;
  const state = call.video_state ? t().videoStates[call.video_state] : null;
  const fps = value => value == null ? null : `${nf.format(value)} ${t().fpsUnit}`;
  return block(t().terminalTitle, [[l.userAgent, norm(call.peer_user_agent)]])
    + block(t().negotiatedTitle, [
      [l.audio, norm(call.audio_codec)],
      [l.video, norm(call.video_encoder) || norm(call.video_codec)],
      [l.direction, directions(call.media_direction)],
    ])
    + block(t().versionTitle, [
      [l.gateway, norm(call.gw_version)], [l.baresip, norm(call.baresip_version)],
      [l.patch, norm(call.baresip_patch)], [l.chromium, norm(call.chromium_version)],
    ])
    + block(t().pictureTitle, [
      [l.state, state],
      [l.minFps, fps(call.video_min_rx_fps)],
      [l.lowIntervals, call.video_low_intervals],
      [l.keyframes, call.video_keyframe_requests],
      [l.presentation, call.presentation_s ? duration(call.presentation_s) : null],
    ])
    + ((call.frame_rates || []).length > 1
      ? `<h3>${esc(t().fpsTitle)}</h3><div data-chart="fps">${timeLines(call.frame_rates, [
          { key: 'rx', label: t().fpsReceived, color: themeColor('--blue') },
          { key: 'tx', label: t().fpsSent, color: themeColor('--mention') },
        ], t().fpsTitle)}</div>`
      : '');
}

function mediaTable(media) {
  if (!media || !media.length) return `<p class="note">${esc(t().noMedia)}</p>`;
  const columns = t().mediaCols;
  return `<table class="media"><thead><tr>${columns.map(c => `<th>${esc(c)}</th>`).join('')}</tr></thead>
    <tbody>${media.map(row => `<tr>
      <td class="mono">${esc(row.media)} ${esc(row.stream_index)}</td>
      <td class="mono">${esc(row.direction)}</td>
      <td class="num">${nf.format(row.packets ?? 0)}</td>
      <td class="num">${nf.format(row.lost_packets ?? 0)}</td>
      <td class="num">${nf.format(row.jitter_ms ?? 0)}</td>
      <td class="num">${nf.format(row.avg_bitrate_kbps ?? 0)}</td>
    </tr>`).join('')}</tbody></table>`;
}

let opener = null;   // the element that opened the drawer, to give focus back to

function closeDrawer() {
  // Called from unmount(), so it must tolerate a template that is already
  // gone: a failure here would abort the navigation itself.
  for (const id of ['callDrawer', 'callScrim', 'callTrace', 'callRaw']) {
    const element = $(id);
    if (element) element.hidden = true;
  }
  // A dialog gives focus back where it took it — if that place still exists.
  if (opener && document.contains(opener)) opener.focus();
  opener = null;
}

async function openDrawer(id) {
  opener = document.activeElement;
  $('callDrawer').hidden = false;
  $('callScrim').hidden = false;
  // Focus moves into the dialog: the close button is its first control.
  $('callClose').focus();
  $('callTrace').hidden = true;
  $('callRaw').hidden = true;
  $('callNumber').textContent = '';
  $('callDrawerBody').innerHTML = `<p class="note">${esc(t().loading)}</p>`;
  try {
    const call = await get(`/api/reporting/calls/${encodeURIComponent(id)}`);
    if (!mounted) return;
    // No link means nothing to open: show nothing rather than a dead button
    // (old capture rotated out, or neither Call-ID nor room usable).
    // A room link is not an exact match, so it gets its own label and a note.
    // The number the search box accepts as "#3197", and the payload as a file.
    $('callNumber').textContent = t().callNumber(call.id);
    $('callRaw').href = `/api/reporting/calls/${encodeURIComponent(call.id)}/raw`;
    $('callRaw').setAttribute('download', '');
    $('callRaw').hidden = false;
    const trace = $('callTrace');
    const exact = call.homer_link_kind === 'exact';
    trace.hidden = !call.homer_url;
    if (call.homer_url) {
      trace.href = call.homer_url;
      trace.textContent = exact ? t().homerTrace : t().homerRoomSearch;
      trace.title = exact ? '' : t().homerRoomHint;
    }
    const dtmf = (call.dtmf_events || []).map(event => esc(event.input)).join(' ');
    // nosemgrep: mgr-innerhtml-unescaped -- every value below goes through esc() (checked with poisoned data, tests/e2e/escaping.mjs)
    $('callDrawerBody').innerHTML = `
      <table class="detail"><tbody>${detailRows(call)}</tbody></table>
      ${mediaDetails(call)}
      <h3>${esc(t().mediaTitle)}</h3>
      ${mediaTable(call.media)}
      ${dtmf ? `<h3>${esc(t().dtmfTitle)}</h3><p class="mono">${dtmf}</p>` : ''}
      ${call.homer_url && !exact ? `<p class="note">${esc(t().homerRoomHint)}</p>` : ''}
      <details><summary>${esc(t().rawTitle)}</summary>
        <pre>${esc(JSON.stringify(call.raw, null, 2))}</pre></details>`;
    attachHover($('callDrawerBody').querySelector('[data-chart="fps"]'));
  } catch (error) {
    if (error.message === 'unauthenticated' || !mounted) return;
    $('callDrawerBody').innerHTML = `<p class="msg err">${esc(errorMessage(error, t()))}</p>`;
  }
}

/* ---------------------------------------------------------- loading */

async function load() {
  const id = ++requestId;
  const query = new URLSearchParams({
    q: $('callSearch').value.trim(),
    start: `${isoOf(range.start)}T${pad(range.from)}:00:00`,
    end: `${isoOf(range.end)}T${pad(range.to)}:59:59.999999`,
    limit: String(PAGE_SIZE),
    offset: String(offset),
  });
  if (reason != null) query.set('reason', reason);
  for (const key of ['outcome', 'video']) {
    const all = LISTS[key].keys;
    if (picked[key].length < all.length) query.set(key, picked[key].join(','));
  }
  // Nothing ticked in a list: nothing to show, and nothing to ask.
  if (!picked.outcome.length || !picked.video.length) {
    total = 0;
    render([]);
    return;
  }
  try {
    const page = await get(`/api/reporting/calls?${query}`);
    // A slow reply must never overwrite the result of a newer query.
    if (!mounted || id !== requestId) return;
    total = page.total;
    render(page.calls);
  } catch (error) {
    if (error.message === 'unauthenticated' || !mounted || id !== requestId) return;
    // nosemgrep: mgr-innerhtml-unescaped -- every value below goes through esc() (checked with poisoned data, tests/e2e/escaping.mjs)
    $('callRows').innerHTML = `<tr><td colspan="${COLUMNS}" class="msg err">${esc(errorMessage(error, t()))}</td></tr>`;
  }
}

function reload() {
  offset = 0;
  load();
}

const LISTS = {
  outcome: { keys: OUTCOME_FILTERS, labels: () => t().outcomes, name: () => t().callsOutcome },
  video: { keys: VIDEO_FILTERS, labels: () => t().videoStates, name: () => t().callsVideo },
};
const PANELS = { outcome: 'callOutcome', video: 'callVideo' };

/* Drawn from the module state, never the other way round: a link from the
   Quality view and the lists always agree. */
function drawFilter() {
  for (const [key, id] of Object.entries(PANELS)) {
    const list = LISTS[key], labels = list.labels();
    $(`${id}List`).innerHTML = list.keys.map(value => `<label>
        <input type="checkbox" value="${esc(value)}"${picked[key].includes(value) ? ' checked' : ''}>
        <span>${esc(labels[value] || value)}</span></label>`).join('');
    const count = picked[key].length;
    $(`${id}Button`).textContent = count === list.keys.length ? t().filterEvery(list.name())
      : count === 0 ? t().filterNothing(list.name())
      : count === 1 ? `${list.name()} : ${labels[picked[key][0]] || picked[key][0]}`
      : t().filterSome(list.name(), count);
  }
  $('callFilter').hidden = reason == null;
  $('callFilterText').textContent = reason ?? '';
  $('callFilterClear').setAttribute('aria-label', t().clearFilter);
}

function pick(key, values) {
  // Kept in the order of the list, whatever the order of the clicks.
  picked[key] = LISTS[key].keys.filter(value => values.includes(value));
  drawFilter();
  reload();
}

function closePanels(event) {
  for (const id of Object.values(PANELS)) {
    const box = $(`${id}Filter`);
    if (box && !box.contains(event.target)) $(`${id}Panel`).hidden = true;
  }
}

function applyLanguage() {
  // The view may have been replaced while its listener was still
  // registered: nothing to translate then.
  if (!mounted || !$('callSearch')) return;
  translate(document);
  $('callSearch').placeholder = t().callsSearch;
  // Icon-only buttons: their name lives here, in the user's language, not
  // in a French aria-label baked into the template.
  $('callPrev').setAttribute('aria-label', t().pagerPrev);
  $('callNext').setAttribute('aria-label', t().pagerNext);
  $('callClose').setAttribute('aria-label', t().close);
  $('callHead').innerHTML = t().callCols.map(column => `<th>${esc(column)}</th>`).join('');
  const selected = $('callPreset').value;
  $('callPreset').innerHTML = Object.keys(PRESETS)
    .map(key => `<option value="${key}">${esc(t().callPresets[key])}</option>`)
    .join('') + `<option value="custom">${esc(t().callPresets.custom)}</option>`;
  $('callPreset').value = selected || 'today';
  drawRange();
  drawFilter();
  calendar.refresh();
  load();
}

export function mount() {
  mounted = true;
  offset = 0;
  // Opened from the Quality view: its period and its exact filter.
  const link = takeJournalFilter();
  reason = link && link.reason != null ? link.reason : null;
  for (const key of ['outcome', 'video']) {
    picked[key] = link && link[key] != null ? [link[key]] : [...LISTS[key].keys];
  }
  $('callPreset').value = link ? 'custom' : 'today';
  range = link
    ? normalise({ start: link.start, end: Math.min(link.end, todayKey()), from: 0, to: 23 })
    : presetRange('today');
  calendar = createCalendar({
    panel: $('callCalendar'), max: todayKey(),
    onApply: ({ start, end }) => setRange({ ...range, start, end }, 'custom'),
  });
  applyLanguage();
  // The preset list is only filled by applyLanguage(): set "custom" after it.
  if (link) $('callPreset').value = 'custom';
  stopListening = onLanguageChange(applyLanguage);

  $('callSearch').addEventListener('input', () => {
    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(reload, DEBOUNCE_MS);
  });
  // A preset fills the dates at once, no panel; "custom" opens the panel on
  // the current window instead of changing it.
  $('callPreset').addEventListener('change', event => {
    const name = event.target.value;
    if (PRESETS[name]) setRange(presetRange(name), name);
    else calendar.open({ start: range.start, end: range.end, picking: 'start', from: $('callFrom') });
  });
  // An hour never touches the days: the window keeps its dates, turns custom.
  $('callFromHour').addEventListener('change', event =>
    setRange({ ...range, from: Number(event.target.value) }, 'custom'));
  $('callToHour').addEventListener('change', event =>
    setRange({ ...range, to: Number(event.target.value) }, 'custom'));
  openFromFields(calendar, () => range, [[$('callFrom'), 'start'], [$('callTo'), 'end']]);
  $('callPrev').addEventListener('click', () => {
    offset = Math.max(0, offset - PAGE_SIZE);
    load();
  });
  $('callNext').addEventListener('click', () => {
    if (offset + PAGE_SIZE < total) { offset += PAGE_SIZE; load(); }
  });
  $('callRows').addEventListener('click', event => {
    if (event.target.closest('.copy')) return;   // copying must not open the drawer
    const row = event.target.closest('tr[data-id]');
    if (row) openDrawer(row.dataset.id);
  });
  $('callFilterClear').addEventListener('click', () => {
    reason = null;
    drawFilter();
    reload();
  });
  for (const [key, id] of Object.entries(PANELS)) {
    $(`${id}Button`).addEventListener('click', () => {
      const panel = $(`${id}Panel`);
      const opening = panel.hidden;
      for (const other of Object.values(PANELS)) $(`${other}Panel`).hidden = true;
      panel.hidden = !opening;
    });
    $(`${id}Panel`).addEventListener('change', event => {
      if (event.target.type !== 'checkbox') return;
      pick(key, [...$(`${id}Panel`).querySelectorAll('input:checked')].map(box => box.value));
    });
    for (const button of $(`${id}Panel`).querySelectorAll('[data-pick]')) {
      button.addEventListener('click', () =>
        pick(key, button.dataset.pick === 'all' ? [...LISTS[key].keys] : []));
    }
  }
  document.addEventListener('click', closePanels);
  $('callClose').addEventListener('click', closeDrawer);
  $('callScrim').addEventListener('click', closeDrawer);
  document.addEventListener('keydown', onEscape);
  enableCopy($('callRows'));
  // Once: the drawer body outlives its contents, and the handler is
  // delegated. Attached on every open, N opens meant N clipboard writes.
  enableCopy($('callDrawerBody'));
}

function onEscape(event) {
  if (event.key === 'Escape') closeDrawer();
}

export function unmount() {
  mounted = false;
  clearTimeout(debounceTimer);
  document.removeEventListener('keydown', onEscape);
  document.removeEventListener('click', closePanels);
  if (calendar) calendar.destroy();
  calendar = null;
  closeDrawer();
  if (stopListening) stopListening();
  stopListening = null;
}
