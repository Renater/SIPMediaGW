/* Quality view: what completed, what did not, and why.

   Two blocks today. The media quality index waits on the gateway sending
   per-call samples: end-of-call aggregates cannot show a call that was fine for
   fifty minutes and unusable for five, which is the case that gets reported. */

import { get, errorMessage, settleAll } from '../api.js';
import { t, translate, onLanguageChange } from '../i18n.js';
import { esc, nf, periodLabel } from '../format.js';
import { fillMonths, press } from '../ui.js';
import { addDays } from '../datepicker.js';
import { openJournal } from '../journal-link.js';

// The month under way by default: the tab is opened to see where things stand.
let period = 'month', stopListening = null, mounted = false;
/* What each drawn row stands for, and the period's window: a click opens the
   Journal on exactly those calls. */
let bounds = null, outcomeRows = [], reasonRows = [], videoRows = [];

const $ = id => document.getElementById(id);

const head = (id, columns) => {
  $(id).innerHTML = columns
    .map((c, i) => `<th${i ? ' class="center"' : ''}>${esc(c)}</th>`).join('');
};

const keyOfIso = iso => Number(String(iso).slice(0, 10).replaceAll('-', ''));

function showCalls(filter) {
  if (!bounds) return;
  // [since, until) in the API, both days included in the Journal.
  openJournal({ start: keyOfIso(bounds.since), end: addDays(keyOfIso(bounds.until), -1), ...filter });
}

const pct = (part, total) => `${((part / (total || 1)) * 100).toFixed(1).replace('.', ',')} %`;

function drawOutcomes(outcomes) {
  head('qOutcomesHead', t().qOutcomeCols);
  const rows = outcomeRows = outcomes.outcomes || [];
  const total = rows.reduce((sum, row) => sum + (row.sessions || 0), 0) || 1;
  $('qOutcomes').innerHTML = rows.length
    ? rows.map((row, index) => `<tr class="selectable" data-index="${index}">
        <td>${esc(t().outcomes[row.outcome] || row.outcome)}</td>
        <td class="center num">${nf.format(row.sessions)}</td>
        <td class="center num">${((row.sessions / total) * 100).toFixed(1).replace('.', ',')} %</td>
        <td class="center num">${nf.format(row.gateway_hours ?? 0)} h</td>
      </tr>`).join('')
    : `<tr><td class="msg" colspan="4">${esc(t().noSessions)}</td></tr>`;
}

/* Close reasons come from baresip and from the network stack, and read as
   system errors. Each row shows a plain sentence, the raw string below it for a
   search in Homer, and what the reason actually produced.

   Listing only the unclassified ones answered a maintainer's question. The one
   a reader has is the other: what ends a call here, and is that normal. A reason
   that ends completed calls is normal however alarming it reads — the conference
   had been joined before it fired. */
function explain(row) {
  const rules = t().reasonMeanings;
  let meaning = t().reasonUnknown;
  for (const [prefix, text] of Object.entries(rules)) {
    if (row.close_reason.startsWith(prefix)) { meaning = text; break; }
  }
  // The same reason appears once per outcome, and without this clause the two
  // rows carry the same sentence while carrying different verdicts — which is
  // exactly what a reader needs explained. "The endpoint hung up" means one
  // thing after a conference and another before reaching one.
  const context = t().outcomeContext[row.outcome];
  // A call that never came up: "the endpoint hung up" or "an IVR abandon"
  // would contradict it. Only a reason that names a fault still says more.
  if (row.outcome === 'not_established' && !row.is_failure) return context;
  return context ? `${meaning} ${context}` : meaning;
}

function verdict(row) {
  // Whatever the reason, a caller who never got in was not served; the reason
  // does not tell (a normal hang-up carries the same one).
  if (row.is_failure || row.outcome === 'not_established') return { label: t().verdictFailure, cls: 'bad' };
  if (row.outcome === 'completed') return { label: t().verdictNormal, cls: 'good' };
  return { label: t().verdictUnclassified, cls: 'warn' };
}

function drawReasons(reasons) {
  head('qReasonsHead', t().qReasonCols);
  reasonRows = reasons || [];
  $('qReasons').innerHTML = reasonRows.length
    ? reasonRows.map((row, index) => {
        const v = verdict(row);
        return `<tr class="selectable" data-index="${index}">
          <td>${esc(explain(row))}<br><span class="mono dim">${esc(row.close_reason)}</span></td>
          <td class="center"><span class="tag ${esc(v.cls)}">${esc(v.label)}</span></td>
          <td class="center num">${nf.format(row.sessions)}</td>
          <td class="center num">${nf.format(row.pct)} %</td>
          <td class="center num">${nf.format(row.avg_occupancy_s ?? 0)} s</td>
        </tr>`;
      }).join('')
    : `<tr><td class="msg" colspan="5">${esc(t().noSessions)}</td></tr>`;
}

const VIDEO_CLASS = { ok: 'good', stalled: 'bad', oneway: 'warn', no_picture: 'bad' };

function drawVideo(video) {
  head('qVideoHead', t().qVideoCols);
  const rows = videoRows = video.states || [];
  const total = rows.reduce((sum, row) => sum + (row.sessions || 0), 0);
  $('qVideo').innerHTML = rows.length
    ? rows.map((row, index) => `<tr class="selectable" data-index="${index}">
        <td>${VIDEO_CLASS[row.video_state]
          ? `<span class="tag ${VIDEO_CLASS[row.video_state]}">${esc(t().videoStates[row.video_state])}</span>`
          : esc(t().videoStates[row.video_state] || row.video_state)}</td>
        <td class="center num">${nf.format(row.sessions)}</td>
        <td class="center num">${pct(row.sessions, total)}</td>
      </tr>`).join('')
    : `<tr><td class="msg" colspan="3">${esc(t().noSessions)}</td></tr>`;
}

async function load() {
  const query = `period=${encodeURIComponent(period)}`;
  const { value, failure } = await settleAll([
    get(`/api/reporting/outcomes?${query}`),
    get(`/api/reporting/ivr-reasons?limit=20&${query}`),
    get(`/api/reporting/video-states?${query}`),
  ], t);
  if (!mounted) return;

  const outcomes = value(0), reasons = value(1), video = value(2);
  bounds = outcomes ? { since: outcomes.since, until: outcomes.until } : null;
  if (outcomes) {
    $('qPeriod').textContent = periodLabel(outcomes.label);
    drawOutcomes(outcomes);
  } else {
    $('qPeriod').textContent = failure(0);
    $('qOutcomes').innerHTML = `<tr><td class="msg err" colspan="4">${esc(failure(0))}</td></tr>`;
  }
  // The reason list is not scoped to the period on purpose: it exists to build
  // the whitelist, and a rare failure needs the whole history to show up.
  if (reasons) drawReasons(reasons);
  else $('qReasons').innerHTML = `<tr><td class="msg err" colspan="5">${esc(failure(1))}</td></tr>`;
  if (video) drawVideo(video);
  else $('qVideo').innerHTML = `<tr><td class="msg err" colspan="3">${esc(failure(2))}</td></tr>`;
}

function reload() {
  load().catch(error => {
    if (error.message !== 'unauthenticated') $('qPeriod').textContent = errorMessage(error, t());
  });
}

/* Presets and the month list are two ways into one period. The module keeps
   it between visits and the template comes back with nothing pressed: both
   controls are drawn from the state, on mount and after each change. */
function syncControls() {
  const month = /^\d{4}-\d{2}$/.test(period);
  press('#qPeriods button', button => !month && button.dataset.period === period);
  $('qMonth').value = month ? period : '';
}

function setPeriod(next) {
  period = next;
  syncControls();
  reload();
}

function applyLanguage() {
  if (!mounted || !$('qOutcomes')) return;
  translate(document);
  fillMonths($('qMonth'));
  syncControls();
  for (const button of document.querySelectorAll('#qPeriods button')) {
    button.textContent = t().periods[button.dataset.period];
  }
  reload();
}

export function mount() {
  mounted = true;
  applyLanguage();
  stopListening = onLanguageChange(applyLanguage);
  for (const button of document.querySelectorAll('#qPeriods button')) {
    button.addEventListener('click', () => setPeriod(button.dataset.period));
  }
  $('qMonth').addEventListener('change', event => {
    if (event.target.value) setPeriod(event.target.value);
  });
  // A row opens the Journal on its calls: an outcome, a reason with its
  // outcome (the same reason ends normal calls too), a video state.
  const rowOf = (event, rows) => {
    const tr = event.target.closest('tr[data-index]');
    return tr ? rows[Number(tr.dataset.index)] : null;
  };
  $('qOutcomes').addEventListener('click', event => {
    const row = rowOf(event, outcomeRows);
    if (row) showCalls({ outcome: row.outcome });
  });
  $('qReasons').addEventListener('click', event => {
    const row = rowOf(event, reasonRows);
    if (row) showCalls({ reason: row.close_reason, outcome: row.outcome });
  });
  $('qVideo').addEventListener('click', event => {
    const row = rowOf(event, videoRows);
    if (row) showCalls({ outcome: 'completed', video: row.video_state });
  });
}

export function unmount() {
  mounted = false;
  if (stopListening) stopListening();
  stopListening = null;
}
