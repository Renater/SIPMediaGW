/* Capacity view: what the pool consumed, and whether it sufficed.

   Everything here reads pool_samples. What costs is the VM, not the container:
   a gateway reporting `free` is a VM that exists and is billed, it simply runs
   nothing. So the cost basis is provisioned = free + idle + ivr + in_call, and
   utilisation is measured against it — computed against warm containers only,
   the rate would flatter the result by ignoring VMs with nothing on them. */

import { get, errorMessage, settleAll } from '../api.js';
import { t, translate, onLanguageChange } from '../i18n.js';
import { esc, nf, periodLabel } from '../format.js';
import { attachHover, hourlyLines, monthlyPairs } from '../charts.js';
import { fillMonths, press } from '../ui.js';

// The month under way by default: the tab is opened to see where things stand.
let period = 'month', dayType = 'default';
let profile = { profile: [], previous: [] }, hours = [], sizing = [], sizingDayType = 'default';
// VM-hours over the period and the part in conference. They replaced a cost in
// euros, which left out the fixed infrastructure and the services around it
// and was read as the cost of the service.
let vmHours = null;
let stopListening = null, mounted = false;

const $ = id => document.getElementById(id);

/* Column headers, with an optional explanation.

   The explanation sits in a title attribute and is lost to a screenshot, which
   is why the short form in the header itself carries what a reader must not
   miss — "high load (95% of the time)" says enough on a slide, and the tooltip
   adds the reasoning for whoever is in front of the tool. */
const head = (id, columns, hints = []) => {
  $(id).innerHTML = columns.map((c, i) => {
    // The explanation rides on the mark, not on a title attribute: the native
    // tooltip is a black single line the pointer can land inside.
    const mark = hints[i]
      ? ` <span class="hint" tabindex="0" role="img" aria-label="${esc(hints[i])}" data-hint="${esc(hints[i])}">?</span>` : '';
    return `<th${i ? ' class="center"' : ''}>${esc(c)}${mark}</th>`;
  }).join('');
};

/* ------------------------------------------------------------ rendering */

function drawProfile() {
  const rows = (profile.profile || []).filter(row => row.day_type === dayType);
  $('capProfile').innerHTML = hourlyLines(rows, [
    { key: 'provisioned_avg', label: t().capProvisioned, color: themeVar('--mention') },
    { key: 'busy_avg', label: t().capBusy, color: themeVar('--blue') },
  ], [], t().capProfileTitle);
  attachHover($('capProfile'));
  $('capProfileTitle').textContent = t().capProfileTitle;
}

const themeVar = name =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim();

function drawPressure(slots) {
  head('capPressureHead', t().capPressureCols, t().capPressureHints);
  const rows = (slots || []).filter(row => Number(row.no_spare_minutes) > 0
                                        || Number(row.cold_start_minutes) > 0);
  if (!rows.length) {
    $('capPressure').innerHTML = `<tr><td class="msg" colspan="4">${esc(t().capNoPressure)}</td></tr>`;
    return;
  }
  $('capPressure').innerHTML = rows.slice(0, 12).map(row => `<tr>
    <td>${esc(t().capDayTypes[row.day_type] || row.day_type)} — ${esc(row.hour)}h</td>
    <td class="center num">${nf.format(row.no_spare_minutes)} min</td>
    <td class="center num">${nf.format(row.cold_start_minutes)} min</td>
    <td class="center num">${nf.format(row.no_spare_pct)} %</td>
  </tr>`).join('');
}

/* Sizing, hour by hour.

   Percentiles over a whole month are dragged down by nights and weekends: most
   samples are zero, so the figure lands far below what the busy hours need, and
   sizing on it under-provisions. Per slot, each hour carries its own
   distribution — and that is the shape the scaler is configured in, so a line
   here reads straight across to a setting.

   The wording avoids percentile names on purpose: this is read by someone
   deciding a budget. "Charge haute" is the level covered 95 % of the time,
   "Pointe" the highest reading of the slot. */
function drawSizing() {
  head('capSizingHead', t().capSizingCols, t().capSizingHints);
  const rows = sizing || [];

  $('capSizingChart').innerHTML = hourlyLines(rows, [
    { key: 'peak', label: t().capPeakLabel, color: themeVar('--mention') },
    { key: 'p95', label: t().capHighLabel, color: themeVar('--blue') },
  ], [], t().capSizingTitle);
  attachHover($('capSizingChart'));

  // Only the slots that carry something: twenty-four rows of zeroes bury the
  // four that matter.
  const busy = rows.filter(row => (Number(row.peak) || 0) > 0);
  $('capSizing').innerHTML = busy.length
    ? busy.map(row => {
        const p95 = Number(row.p95) || 0;
        const peak = Number(row.peak) || 0;
        return `<tr>
          <td>${String(row.hour).padStart(2, '0')}h</td>
          <td class="center num">${nf.format(Number(row.median) || 0)}</td>
          <td class="center num"><b>${nf.format(p95)}</b></td>
          <td class="center num">${nf.format(peak)}</td>
          <td class="center num">${nf.format(Math.ceil(p95))}</td>
          <td class="center num">${peak > p95 ? '+' + nf.format(Math.round((peak - p95) * 10) / 10) : '—'}</td>
        </tr>`;
      }).join('')
    : `<tr><td class="msg" colspan="6">${esc(t().noData)}</td></tr>`;
}

const hoursText = value => `${nf.format(Number(value) || 0)} h`;

/* VM-hours over the period, and below them the part spent in a conference —
   the same two figures as the monthly bars, for the period on screen. */
function drawVmHours() {
  const known = vmHours && vmHours.provisioned_hours != null;
  $('cVmHours').textContent = known ? hoursText(vmHours.provisioned_hours) : '—';
  const coverage = known && vmHours.coverage_pct != null && Number(vmHours.coverage_pct) < 95
    ? ' · ' + t().capVmHoursCoverage(Math.round(Number(vmHours.coverage_pct))) : '';
  $('cVmHoursDetail').textContent = known ? t().capVmHoursDetail(hoursText(vmHours.call_hours)) + coverage : '';
}

function drawHours() {
  // Two bars per month: VM hours billed, conference hours served. The gap is
  // the margin left to optimise, and it is the whole point of the chart.
  const rows = (hours || []).map(row => ({
    month: String(row.month).slice(0, 7),
    provisioned_hours: Number(row.provisioned_hours) || 0,
    call_hours: Number(row.call_hours) || 0,
    // A month the Manager spent partly down shows fewer hours for a reason
    // that has nothing to do with the pool: said under its bar.
    coverage: Number(row.coverage_pct) < 95 ? Math.round(Number(row.coverage_pct) || 0) : null,
  }));
  $('capHours').innerHTML = monthlyPairs(rows, [
    { key: 'provisioned_hours', label: t().capVmHours, color: themeVar('--mention') },
    { key: 'call_hours', label: t().capCallHours, color: themeVar('--blue') },
  ], t().capHoursTitle);
}

/* --------------------------------------------------------------- loading */

async function load() {
  const query = `period=${encodeURIComponent(period)}`;
  const { value, failure } = await settleAll([
    get(`/api/reporting/pool-profile?${query}&compare=false`),
    get(`/api/reporting/pool-pressure?${query}`),
    get('/api/reporting/pool-hours?months=12'),
    get(`/api/reporting/concurrency/hourly?${query}&dayType=${sizingDayType}`),
    get(`/api/reporting/pool-period-hours?${query}`),
  ], t);
  if (!mounted) return;

  const p = value(0), pressure = value(1), h = value(2), s = value(3);
  vmHours = value(4);
  drawVmHours();

  if (p) {
    profile = p;
    $('capPeriod').textContent = periodLabel(p.label);
    drawProfile();
    fillTiles(p.profile || []);
  } else {
    $('capPeriod').textContent = failure(0);
    $('capProfile').innerHTML = `<div class="msg err">${esc(failure(0))}</div>`;
    for (const id of ['cProvisioned', 'cBusy', 'cUtil']) $(id).textContent = '—';
  }

  if (pressure) drawPressure(pressure.slots);
  else $('capPressure').innerHTML = `<tr><td class="msg err" colspan="4">${esc(failure(1))}</td></tr>`;

  if (h) { hours = h; drawHours(); }
  else $('capHours').innerHTML = `<div class="msg err">${esc(failure(2))}</div>`;

  if (s) { sizing = s.hours || []; drawSizing(); }
  else $('capSizing').innerHTML = `<tr><td class="msg err" colspan="6">${esc(failure(3))}</td></tr>`;
}

/* The headline figures describe the working days: a weekend average would drag
   them toward a floor that says nothing about how the service is sized. */
function fillTiles(rows) {
  const working = rows.filter(row => row.day_type === 'default');
  const sum = key => working.reduce((total, row) => total + (Number(row[key]) || 0), 0);
  const count = working.length || 1;

  $('cProvisioned').textContent = nf.format(Math.round(sum('provisioned_avg') / count * 10) / 10);
  $('cBusy').textContent = nf.format(Math.max(0, ...working.map(row => Number(row.busy_peak) || 0)));
  const provisioned = sum('provisioned_avg');
  $('cUtil').textContent = provisioned
    ? `${nf.format(Math.round(100 * sum('busy_avg') / provisioned * 10) / 10)} %` : '—';
}

function reload() {
  load().catch(error => {
    if (error.message !== 'unauthenticated') $('capPeriod').textContent = errorMessage(error, t());
  });
}

/* Period, month and the two day-type switches live in module state across
   visits; the template comes back with nothing pressed. Every control is
   drawn from the state, on mount and after each change. */
function syncControls() {
  const month = /^\d{4}-\d{2}$/.test(period);
  press('#capPeriods button', button => !month && button.dataset.period === period);
  $('capMonth').value = month ? period : '';
  press('#capDayType button', button => button.dataset.daytype === dayType);
  press('#capSizingDayType button', button => button.dataset.daytype === sizingDayType);
}

function setPeriod(next) {
  period = next;
  syncControls();
  reload();
}

function applyLanguage() {
  if (!mounted || !$('capProfile')) return;
  translate(document);
  fillMonths($('capMonth'));
  syncControls();
  ['cProvisioned', 'cBusy', 'cUtil', 'cVmHours'].forEach((id, index) => {
    $(id).nextElementSibling.textContent = t().capTiles[index];
  });
  for (const button of document.querySelectorAll('#capPeriods button')) {
    button.textContent = t().periods[button.dataset.period];
  }
  for (const selector of ['#capDayType button', '#capSizingDayType button']) {
    for (const button of document.querySelectorAll(selector)) {
      button.textContent = t().capDayShort[button.dataset.daytype];
      button.title = t().capDayTypes[button.dataset.daytype];
    }
  }
  drawProfile();
  drawSizing();
  drawVmHours();
  reload();
}

export function mount() {
  mounted = true;
  applyLanguage();
  stopListening = onLanguageChange(applyLanguage);

  for (const button of document.querySelectorAll('#capPeriods button')) {
    button.addEventListener('click', () => setPeriod(button.dataset.period));
  }
  $('capMonth').addEventListener('change', event => {
    if (event.target.value) setPeriod(event.target.value);
  });
  for (const button of document.querySelectorAll('#capSizingDayType button')) {
    button.addEventListener('click', () => {
      sizingDayType = button.dataset.daytype;
      syncControls();
      reload();
    });
  }
  for (const button of document.querySelectorAll('#capDayType button')) {
    button.addEventListener('click', () => {
      dayType = button.dataset.daytype;
      syncControls();
      drawProfile();
    });
  }
}

export function unmount() {
  mounted = false;
  if (stopListening) stopListening();
  stopListening = null;
}
