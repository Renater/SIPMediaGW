/* Usage report: one period at a time, plus the monthly series.
   All four calls share the same period parameter, so the figures on screen
   always describe the same window. */

import { get, errorMessage, settleAll } from '../api.js';
import { t, translate, onLanguageChange } from '../i18n.js';
import { esc, nf, periodLabel, formatDuration } from '../format.js';
import { renderDonut, histogram, themeColor } from '../charts.js';
import { platformLabel, isKnownPlatform, platformColor } from '../platforms.js';
import { fillMonths, press } from '../ui.js';

/* Periods that are still running: only these are worth polling. A closed
   period cannot change, so the report stays put and prints as it is read. */
const LIVE_PERIODS = new Set(['today', 'week', 'month']);
const REFRESH_MS = 30000;

let monthly = { months: [], trend_hours: [] };
let metric = 'hours', period = 'today';
// Every unit ticked is the default, and sends nothing: filtering on the full
// list and filtering on nothing must give the same totals.
let allUnits = [], selectedUnits = null;
let stopListening = null, refreshTimer = null, mounted = false;

const $ = id => document.getElementById(id);


function drawHistogram() {
  const unit = metric === 'hours' ? t().unitHours : t().unitCalls;
  $('histogram').innerHTML = histogram(monthly.months, monthly.trend_hours || [], metric, false,
                                       t().histMonthly(unit));
  $('histTitle').textContent = t().histMonthly(unit);
}

async function loadPeriod(next) {
  // Nothing ticked means nothing to show. Sending an empty units= would read as
  // "no filter" on the server and quietly display everything, which is the
  // opposite of what was asked.
  if (selectedUnits && selectedUnits.length === 0) return clearBlocks();
  const unitParam = (selectedUnits && selectedUnits.length < allUnits.length)
    ? `&units=${encodeURIComponent(selectedUnits.join(','))}` : '';
  const query = `period=${encodeURIComponent(next)}${unitParam}`;
  // allSettled: a missing table or a failing route blanks its own section,
  // never the whole report.
  const { value, failure } = await settleAll([
    get(`/api/reporting/summary?${query}`),
    get(`/api/reporting/org-units?${query}`),
    get(`/api/reporting/platforms?${query}`),
  ], t);
  if (!mounted) return;
  const summary = value(0), units = value(1), platforms = value(2);
  if (!summary) { $('period').textContent = failure(0);
    for (const id of ['tCalls', 'tHours', 'tPeak']) $(id).textContent = '—'; }

  if (summary) {
  $('period').textContent = periodLabel(summary.label);
  $('tCalls').textContent = nf.format(summary.calls || 0);
  $('tHours').textContent = formatDuration(summary.seconds || 0);
  $('tPeak').textContent = nf.format(summary.peak_concurrent || 0);
  }

  if (units) {
    // The list is rebuilt from any unfiltered answer, not only the first one:
    // if the first load failed, nothing would ever repopulate the boxes.
    // A filtered answer is never used for it — the unticked units are missing
    // from it, and reading it would erase them from the list.
    if (!unitParam) {
      const seen = (units.units || []).map(row => row.org_unit);
      if (seen.length) {
        // The module keeps its state across mounts, but the DOM does not: coming
        // back from another tab leaves the boxes to be drawn again even when the
        // list is unchanged. Redrawing is cheap; deciding when to skip it is how
        // the panel ended up empty.
        if (seen.join() !== allUnits.join()) {
          allUnits = seen;
          selectedUnits = [...allUnits];
        }
        renderUnitFilter();
      }
    }
    renderDonut('lgUnits', 'dnUnits', units.units || [], 'org_unit');
  }
  if (platforms) {
    // Display names and icons come from the shared platform table, so the
    // legend reads like the pool table and the call log.
    // Everything the connector table does not know goes into one bucket: a
    // legend listing "slidestreamer" next to Teams invites the question of what
    // product that is, and the answer is that it is not one.
    const known = platforms.filter(row => isKnownPlatform(row.platform));
    const rest = platforms.filter(row => !isKnownPlatform(row.platform));
    const restCalls = rest.reduce((sum, row) => sum + (Number(row.calls) || 0), 0);
    const named = known.map(row => ({ ...row, label: platformLabel(row.platform),
                                      color: platformColor(row.platform) }));
    if (restCalls) {
      named.push({ platform: '(other)', label: t().platformOther, calls: restCalls,
                   color: themeColor('--other'),
                   hours: rest.reduce((sum, row) => sum + (Number(row.hours) || 0), 0) });
    }
    renderDonut('lgPlatforms', 'dnPlatforms', named, 'platform', { icons: true, labelKey: 'label' });
  }
}

function clearBlocks() {
  for (const id of ['tCalls', 'tHours', 'tPeak']) $(id).textContent = '—';
  renderDonut('lgUnits', 'dnUnits', [], 'org_unit');
  renderDonut('lgPlatforms', 'dnPlatforms', [], 'platform');
}

function renderUnitFilter() {
  // The search narrows what is shown, never what is selected: a unit filtered
  // out of the list stays ticked, so typing cannot silently drop it from the
  // figures.
  const needle = ($('unitSearch').value || '').trim().toLowerCase();
  const shown = needle ? allUnits.filter(u => u.toLowerCase().includes(needle)) : allUnits;
  $('unitList').innerHTML = shown.length
    ? shown.map(unit => `<label>
        <input type="checkbox" value="${esc(unit)}"${selectedUnits.includes(unit) ? ' checked' : ''}>
        <span>${esc(unit)}</span></label>`).join('')
    : `<div class="msg">${esc(t().unitsNoMatch)}</div>`;
  updateUnitButton();
}

function updateUnitButton() {
  $('unitButton').textContent = selectedUnits.length === allUnits.length
    ? t().unitsAllLabel : t().unitsLabel(selectedUnits.length);
}

/* Presets and the month list are two ways into the same period parameter:
   choosing one clears the other so the header always shows what is displayed.
   Period and metric live in module state across visits; the template comes
   back with nothing pressed and an empty month list. Every control is drawn
   from the state, on mount and after each change. */
function syncControls() {
  const month = /^\d{4}-\d{2}$/.test(period);
  press('.periods button', button => !month && button.dataset.period === period);
  $('month').value = month ? period : '';
  press('.switch button[data-metric]', button => button.dataset.metric === metric);
}

function setPeriod(next) {
  period = next;
  syncControls();
  scheduleRefresh();
  reload();
}

function reload() {
  loadPeriod(period).catch(error => {
    if (error.message !== 'unauthenticated') $('period').textContent = errorMessage(error, t());
  });
}

/* No button and no countdown here: a report is read, not monitored. It simply
   keeps itself current when the period it shows is still running. */
function scheduleRefresh() {
  clearInterval(refreshTimer);
  refreshTimer = LIVE_PERIODS.has(period) ? setInterval(reload, REFRESH_MS) : null;
}

function applyLanguage() {
  // The view may have been replaced while its listener was still
  // registered: nothing to translate then.
  if (!mounted || !$('histTitle')) return;
  translate(document);
  fillMonths($('month'));
  if ($('unitSearch')) $('unitSearch').placeholder = t().unitsSearch;
  for (const node of document.querySelectorAll('[data-tile]')) {
    node.textContent = t().reportTiles[Number(node.dataset.tile)];
  }
  for (const button of document.querySelectorAll('.periods button')) {
    button.textContent = t().periods[button.dataset.period];
  }
  document.querySelector('.switch button[data-metric="hours"]').textContent = t().metricHours;
  document.querySelector('.switch button[data-metric="calls"]').textContent = t().metricCalls;
  drawHistogram();
  setPeriod(period);
}

function closeUnitPanel(event) {
  const filter = $('unitFilter');
  if (filter && !filter.contains(event.target)) $('unitPanel').hidden = true;
}

export async function mount() {
  mounted = true;
  applyLanguage();
  stopListening = onLanguageChange(applyLanguage);

  // Named from the first paint: it stayed empty until the first reply, and
  // for good if that reply failed.
  $('unitButton').textContent = t().unitsAllLabel;
  $('unitButton').addEventListener('click', () => {
    $('unitPanel').hidden = !$('unitPanel').hidden;
  });
  document.addEventListener('click', closeUnitPanel);
  // The module keeps allUnits between visits but the DOM is rebuilt each time:
  // without this, coming back from another tab shows an empty list until the
  // page is reloaded.
  if (allUnits.length) renderUnitFilter();
  $('unitSearch').addEventListener('input', renderUnitFilter);
  $('unitPanel').addEventListener('change', event => {
    if (event.target.type !== 'checkbox') return;
    selectedUnits = [...$('unitPanel').querySelectorAll('input:checked')].map(box => box.value);
    updateUnitButton();
    reload();
  });
  for (const button of $('unitPanel').querySelectorAll('[data-units]')) {
    button.addEventListener('click', () => {
      selectedUnits = button.dataset.units === 'all' ? [...allUnits] : [];
      renderUnitFilter();
      reload();
    });
  }
  $('month').addEventListener('change', event => {
    if (event.target.value) setPeriod(event.target.value);
  });
  for (const button of document.querySelectorAll('.periods button')) {
    button.addEventListener('click', () => setPeriod(button.dataset.period));
  }
  for (const button of document.querySelectorAll('.switch button')) {
    button.addEventListener('click', () => {
      if (button.dataset.metric) {
        metric = button.dataset.metric;
        syncControls();
      }
      drawHistogram();
    });
  }

  try {
    monthly = await get('/api/reporting/monthly?months=24');
    drawHistogram();
  } catch (error) {
    if (error.message === 'unauthenticated') throw error;
    $('histogram').innerHTML = `<div class="msg err">${esc(errorMessage(error, t()))}</div>`;
  }
}

export function unmount() {
  mounted = false;
  clearInterval(refreshTimer);
  refreshTimer = null;
  if (stopListening) stopListening();
  stopListening = null;
  // Added on document by mount(): left there, every visit stacked one more.
  document.removeEventListener('click', closeUnitPanel);
}
