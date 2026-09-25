/* Inline SVG charts.
   Written by hand rather than pulled from a library: the page must render on
   an air-gapped deployment and print cleanly. */

import { esc, nf, monthLabel } from './format.js';
import { t } from './i18n.js';
import { platformIcon, attachIconFallback } from './platforms.js';

/* DSFR categorical palette (blue, foam, bud, sunflower, clay, wisteria,
   emerald, caramel, macaroon). */
const PALETTE = ['#000091', '#465f9d', '#68a532', '#c8aa39', '#e4794a',
                 '#a558a0', '#00a95f', '#c08c65', '#e18b76'];
const UNASSIGNED = new Set(['(unassigned)', '(none)', '(inconnue)']);

export const themeColor = name =>
  getComputedStyle(document.documentElement).getPropertyValue(name).trim();

// Colours are interpolated into attributes (stroke, fill, data-color). They
// come from the palette or from CSS variables today; this keeps it that way
// if a caller ever hands one over from data. Anything else renders as no colour.
const COLOR = /^(#[0-9a-f]{3,8}|rgba?\([\d\s.,%]+\))$/i;
const safeColor = value => (COLOR.test(String(value || '').trim()) ? String(value).trim() : '');

function donutSvg(entries, total) {
  const size = 210, radius = 82, thickness = 34, center = size / 2;
  if (!total) {
    return `<svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" aria-hidden="true">
      <circle cx="${center}" cy="${center}" r="${radius}" fill="none"
              stroke="${themeColor('--grid')}" stroke-width="${thickness}"/>
      <text x="${center}" y="${center}" text-anchor="middle" dominant-baseline="central"
            font-size="13" fill="${themeColor('--mention')}">${esc(t().noValue)}</text></svg>`;
  }
  let angle = -Math.PI / 2;
  const arcs = entries.map(entry => {
    // A full circle cannot be drawn with one arc: a single slice becomes a ring.
    if (entries.length === 1) {
      return `<circle cx="${center}" cy="${center}" r="${radius}" fill="none"
                      stroke="${safeColor(entry.color)}" stroke-width="${thickness}"/>`;
    }
    const sweep = (entry.value / total) * Math.PI * 2;
    const x1 = center + radius * Math.cos(angle), y1 = center + radius * Math.sin(angle);
    angle += sweep;
    const x2 = center + radius * Math.cos(angle), y2 = center + radius * Math.sin(angle);
    return `<path d="M ${x1.toFixed(2)} ${y1.toFixed(2)} A ${radius} ${radius} 0 ${sweep > Math.PI ? 1 : 0} 1 ${x2.toFixed(2)} ${y2.toFixed(2)}"
                  fill="none" stroke="${safeColor(entry.color)}" stroke-width="${thickness}"><title>${esc(entry.name)} — ${nf.format(entry.value)}</title></path>`;
  }).join('');
  return `<svg viewBox="0 0 ${size} ${size}" width="${size}" height="${size}" aria-hidden="true">${arcs}
    <text x="${center}" y="${center - 8}" text-anchor="middle" font-size="26" font-weight="700"
          fill="${themeColor('--text')}">${nf.format(total)}</text>
    <text x="${center}" y="${center + 14}" text-anchor="middle" font-size="12"
          fill="${themeColor('--mention')}">Total</text></svg>`;
}

export function renderDonut(legendId, chartId, rows, nameKey, { icons = false, labelKey = null } = {}) {
  const entries = rows
    .map(row => ({ key: row[nameKey], name: (labelKey && row[labelKey]) || row[nameKey],
                   color: null, value: Number(row.calls) || 0 }))
    .filter(entry => entry.value > 0)
    .sort((a, b) => b.value - a.value);
  const total = entries.reduce((sum, entry) => sum + entry.value, 0);
  entries.forEach((entry, index) => {
    // Unassigned traffic is always grey: it is a gap in the rules, not a unit.
    // A colour set by the caller wins: platforms carry a fixed one so a slice
    // does not change colour between two periods.
    entry.color = entry.color
      || (UNASSIGNED.has(entry.name) ? themeColor('--neutral') : PALETTE[index % PALETTE.length]);
  });
  document.getElementById(chartId).innerHTML = donutSvg(entries, total);
  const legend = document.getElementById(legendId);
  legend.innerHTML = entries.length
    ? entries.map(entry => `<div><i data-color="${safeColor(entry.color)}"></i>
        ${icons ? platformIcon(entry.key) : ''}
        <span class="name">${esc(entry.name)}</span>
        <span class="pct">${nf.format(entry.value)} · ${((entry.value / total) * 100).toFixed(1).replace('.', ',')} %</span></div>`).join('')
    : '<div class="pct">—</div>';
  if (icons) attachIconFallback(legend);
  // Colours are applied through the CSSOM: a style attribute would be blocked
  // by the strict Content-Security-Policy the Manager serves.
  for (const swatch of legend.querySelectorAll('i[data-color]')) {
    swatch.style.background = swatch.dataset.color;
  }
}

export function histogram(months, trend, metric, cumulative, label = '') {
  const width = 1040, height = 300, padLeft = 58, padRight = 16, padTop = 28, padBottom = 34;
  if (!months.length) return `<div class="msg">${esc(t().noData)}</div>`;

  const key = cumulative ? (metric === 'hours' ? 'cumulative_hours' : 'cumulative_calls')
                         : (metric === 'hours' ? 'hours' : 'calls');
  const values = months.map(month => Number(month[key]) || 0);
  // The trend is fitted on monthly hours, so it is meaningless on other views.
  const showTrend = !cumulative && metric === 'hours' && trend.length === months.length;
  const peak = Math.max(...values, ...(showTrend ? trend : [0]), 1);
  const plotWidth = width - padLeft - padRight, plotHeight = height - padTop - padBottom;
  const step = plotWidth / months.length, barWidth = Math.min(38, step * 0.62);
  const y = value => padTop + plotHeight - (value / peak) * plotHeight;
  const axis = themeColor('--axis');

  const ticks = gridTicks([0, 0.25, 0.5, 0.75, 1], peak, y, padLeft, width - padRight, 12,
                          value => nf.format(Math.round(value)));

  const bars = months.map((month, index) => {
    const value = values[index];
    const x = padLeft + step * index + (step - barWidth) / 2;
    const top = y(value);
    const label = `${nf.format(value)} ${metric === 'hours' ? 'h' : t().unitCalls}`;
    return `<rect x="${x.toFixed(1)}" y="${top.toFixed(1)}" width="${barWidth.toFixed(1)}"
                  height="${Math.max(0, padTop + plotHeight - top).toFixed(1)}" fill="${themeColor('--bar')}">
              <title>${esc(monthLabel(month.month, true))} — ${label}</title></rect>
            <text x="${(x + barWidth / 2).toFixed(1)}" y="${(top - 5).toFixed(1)}" text-anchor="middle"
                  font-size="10" fill="${themeColor('--bar')}">${nf.format(Math.round(value))}</text>
            <text x="${(x + barWidth / 2).toFixed(1)}" y="${height - padBottom + 16}" text-anchor="middle"
                  font-size="12" fill="${axis}">${esc(monthLabel(month.month))}</text>`;
  }).join('');

  // Year separators, so a long series stays readable.
  const separators = months.map((month, index) => {
    if (index === 0 || month.month.slice(0, 4) === months[index - 1].month.slice(0, 4)) return '';
    const x = padLeft + step * index;
    return `<line x1="${x.toFixed(1)}" x2="${x.toFixed(1)}" y1="${padTop}" y2="${padTop + plotHeight}"
                  stroke="${themeColor('--neutral')}" stroke-dasharray="4 4"/>
            <text x="${(x + 6).toFixed(1)}" y="${padTop + 12}" font-size="13" font-weight="700"
                  fill="${axis}">${esc(month.month.slice(0, 4))}</text>`;
  }).join('');

  const trendLine = showTrend
    ? `<polyline fill="none" stroke="${themeColor('--trend')}" stroke-width="3" stroke-dasharray="9 6" stroke-linecap="round"
                 points="${trend.map((value, index) => `${(padLeft + step * index + step / 2).toFixed(1)},${y(value).toFixed(1)}`).join(' ')}"/>`
    : '';

  return `<svg viewBox="0 0 ${width} ${height}" width="100%" role="img" aria-label="${esc(label)}">${ticks}${separators}${bars}${trendLine}</svg>`;
}


export function hourlyLines(rows, series, previous = [], label = '', previousLabel = '') {
  const width = 1040, height = 280, padLeft = 46, padRight = 16, padTop = 16, padBottom = 34;
  if (!rows.length) return `<div class="msg">${esc(t().noData)}</div>`;

  const hours = Array.from({ length: 24 }, (_, h) => h);
  const byHour = new Map(rows.map(row => [Number(row.hour), row]));
  const prevByHour = new Map(previous.map(row => [Number(row.hour), row]));
  const value = (map, hour, key) => {
    const row = map.get(hour);
    return row ? Number(row[key]) || 0 : 0;
  };

  // Both periods set the scale: computed on the current one alone, a busier
  // previous month was drawn past the top of the chart, or out of it.
  const peak = Math.max(1, ...series.flatMap(s => hours.flatMap(h =>
    [value(byHour, h, s.key), value(prevByHour, h, s.key)])));
  const plotWidth = width - padLeft - padRight, plotHeight = height - padTop - padBottom;
  const x = hour => padLeft + (hour / 23) * plotWidth;
  const y = v => padTop + plotHeight - (v / peak) * plotHeight;
  const axis = themeColor('--axis');

  const ticks = gridTicks([0, 0.5, 1], peak, y, padLeft, width - padRight, 11,
                          v => nf.format(Math.round(v * 10) / 10));

  const hourLabels = hours.filter(h => h % 3 === 0).map(h =>
    `<text x="${x(h).toFixed(1)}" y="${height - padBottom + 16}" text-anchor="middle" font-size="11" fill="${axis}">${h}h</text>`
  ).join('');

  // The previous period, when asked for: same colours, fainter and dotted —
  // the dots carry the difference where the colour does not (grey scale, a
  // screenshot). There to show movement; the legend and a tooltip name it.
  const ghostName = s => `${s.label} · ${previousLabel || t().capPreviousPeriod}`;
  const ghosts = previous.length ? series.map(s =>
    `<polyline fill="none" stroke="${safeColor(s.color)}" stroke-width="1.5" stroke-dasharray="5 4" opacity="0.45"
               points="${hours.map(h => `${x(h).toFixed(1)},${y(value(prevByHour, h, s.key)).toFixed(1)}`).join(' ')}"><title>${esc(ghostName(s))}</title></polyline>`
  ).join('') : '';

  const lines = series.map(s =>
    `<polyline fill="none" stroke="${safeColor(s.color)}" stroke-width="2.5" stroke-linejoin="round"
               points="${hours.map(h => `${x(h).toFixed(1)},${y(value(byHour, h, s.key)).toFixed(1)}`).join(' ')}"/>` +
    hours.map(h => `<circle cx="${x(h).toFixed(1)}" cy="${y(value(byHour, h, s.key)).toFixed(1)}" r="2.5" fill="${safeColor(s.color)}"/>`).join('')
  ).join('');

  // Hover: one invisible band per hour catches the pointer anywhere in the
  // plot; attachHover() moves a guide to the band's hour and shows every
  // series' value there. The values ride on the band as data, one per series,
  // in the order of `series`, so the box can colour each line.
  const band = plotWidth / 23;
  const bands = hours.map(h => {
    const days = Number((byHour.get(h) || {}).days) || 0;
    const values = series.map(s => nf.format(value(byHour, h, s.key))).join('|');
    return `<rect class="hover-band" x="${(x(h) - band / 2).toFixed(1)}" y="${padTop}" width="${band.toFixed(1)}"
                  height="${plotHeight}" fill="transparent" data-x="${x(h).toFixed(1)}" data-hour="${h}h"
                  data-values="${esc(values)}" data-days="${days ? esc(t().capDaysShort(days)) : ''}"/>`;
  }).join('');
  const guide = hoverGuide(padTop, plotHeight);
  const seriesData = seriesAttribute(series);

  // The legend is drawn inside the SVG, not beside it: it must survive the
  // screenshot.
  const step = previous.length ? 230 : 190;
  const entry = (i, color, text, ghost) =>
    `<line x1="${padLeft + i * step}" x2="${padLeft + i * step + 22}" y1="${height - 6}" y2="${height - 6}"
           stroke="${safeColor(color)}" stroke-width="${ghost ? 1.5 : 2.5}"${ghost ? ' stroke-dasharray="5 4" opacity="0.45"' : ''}/>
     <text x="${padLeft + i * step + 30}" y="${height - 2}" font-size="12" fill="${axis}">${esc(text)}</text>`;
  const legend = series.map((s, i) => entry(i, s.color, s.label, false)).join('')
    + (previous.length ? series.map((s, i) => entry(series.length + i, s.color, ghostName(s), true)).join('') : '');

  return `<svg viewBox="0 0 ${width} ${height + 10}" width="100%" role="img" aria-label="${esc(label)}"
               data-series="${seriesData}">${ticks}${hourLabels}${ghosts}${guide}${lines}${legend}${bands}</svg>`;
}

/* Values over the seconds of one call: the frames per second of the drawer.

   `points` are intervals ending at `t` (seconds of the call), each with one
   value per series, or null where the gateway did not say — drawn as a gap,
   never as zero. Intervals where a presentation ran are shaded: a camera
   picture that dips as slides start is expected, not a fault. The dashed
   line is the threshold under which an interval counts as low. Same hover
   as hourlyLines(), through attachHover(). */
export function timeLines(points, series, label = '', threshold = 5) {
  // Drawn for the drawer (560 px at most): a viewBox of that size keeps the
  // text at its nominal size instead of shrinking it by half.
  const width = 520, height = 200, padLeft = 34, padRight = 10, padTop = 12, padBottom = 34;
  if (points.length < 2) return '';
  const last = Math.max(...points.map(p => Number(p.t) || 0));
  const first = Math.min(...points.map(p => (Number(p.t) || 0) - (Number(p.seconds) || 0)));
  const peak = Math.max(threshold * 2, ...series.flatMap(s => points.map(p => Number(p[s.key]) || 0)));
  const plotWidth = width - padLeft - padRight, plotHeight = height - padTop - padBottom;
  const x = v => padLeft + ((v - first) / Math.max(1, last - first)) * plotWidth;
  const y = v => padTop + plotHeight - (v / peak) * plotHeight;
  const axis = themeColor('--axis'), grid = themeColor('--grid');
  const clock = seconds => `${Math.floor(seconds / 60)}:${String(Math.round(seconds % 60)).padStart(2, '0')}`;

  const ticks = gridTicks([0, 0.5, 1], peak, y, padLeft, width - padRight, 11, v => nf.format(Math.round(v)));
  const limit = `<line x1="${padLeft}" x2="${width - padRight}" y1="${y(threshold).toFixed(1)}" y2="${y(threshold).toFixed(1)}"
                       stroke="${axis}" stroke-dasharray="2 4"/>`;
  const timeLabels = [0, 0.25, 0.5, 0.75, 1].map(ratio => {
    const v = first + ratio * (last - first);
    return `<text x="${x(v).toFixed(1)}" y="${height - padBottom + 16}" text-anchor="middle" font-size="11" fill="${axis}">${clock(v)}</text>`;
  }).join('');
  const shades = points.filter(p => p.presentation).map(p =>
    `<rect x="${x(p.t - p.seconds).toFixed(1)}" y="${padTop}" width="${(x(p.t) - x(p.t - p.seconds)).toFixed(1)}"
           height="${plotHeight}" fill="${grid}" opacity="0.6"/>`).join('');

  // One polyline per run of known values: a null breaks the line.
  const lines = series.map(s => {
    const runs = [[]];
    for (const p of points) {
      if (p[s.key] == null) { if (runs[runs.length - 1].length) runs.push([]); continue; }
      runs[runs.length - 1].push(`${x(p.t).toFixed(1)},${y(Number(p[s.key])).toFixed(1)}`);
    }
    return runs.filter(run => run.length).map(run => run.length === 1
      ? `<circle cx="${run[0].split(',')[0]}" cy="${run[0].split(',')[1]}" r="2.5" fill="${safeColor(s.color)}"/>`
      : `<polyline fill="none" stroke="${safeColor(s.color)}" stroke-width="2" stroke-linejoin="round" points="${run.join(' ')}"/>`
    ).join('');
  }).join('');

  const bands = points.map((p, i) => {
    const left = i ? (x(points[i - 1].t) + x(p.t)) / 2 : padLeft;
    const right = i < points.length - 1 ? (x(p.t) + x(points[i + 1].t)) / 2 : width - padRight;
    const values = series.map(s => p[s.key] == null ? '—' : nf.format(p[s.key])).join('|');
    return `<rect class="hover-band" x="${left.toFixed(1)}" y="${padTop}" width="${Math.max(1, right - left).toFixed(1)}"
                  height="${plotHeight}" fill="transparent" data-x="${x(p.t).toFixed(1)}" data-hour="${clock(p.t)}"
                  data-values="${esc(values)}" data-days="${p.presentation ? esc(t().fpsPresentation) : ''}"/>`;
  }).join('');
  const guide = hoverGuide(padTop, plotHeight);
  const seriesData = seriesAttribute(series);
  const legend = series.map((s, i) =>
    `<line x1="${padLeft + i * 130}" x2="${padLeft + i * 130 + 22}" y1="${height - 6}" y2="${height - 6}" stroke="${safeColor(s.color)}" stroke-width="2.5"/>
     <text x="${padLeft + i * 130 + 30}" y="${height - 2}" font-size="12" fill="${axis}">${esc(s.label)}</text>`).join('');

  return `<svg viewBox="0 0 ${width} ${height + 10}" width="100%" role="img" aria-label="${esc(label)}"
               data-series="${seriesData}">${shades}${ticks}${limit}${timeLabels}${guide}${lines}${legend}${bands}</svg>`;
}

/* The hover box of hourlyLines(): call after each draw, on the element the
   chart was drawn into. Built with the DOM and the CSSOM only — the page's
   Content-Security-Policy allows neither inline styles nor inline handlers. */
export function attachHover(container) {
  const svg = container && container.querySelector('svg[data-series]');
  if (!svg) return;
  const series = svg.dataset.series.split('|').map(item => item.split('~'));
  const guide = svg.querySelector('.hover-guide');
  const tip = document.createElement('div');
  tip.classList.add('chart-tip');
  tip.hidden = true;
  container.classList.add('chart-host');
  container.appendChild(tip);

  const hide = () => { tip.hidden = true; guide.setAttribute('visibility', 'hidden'); };
  svg.addEventListener('mouseleave', hide);
  svg.addEventListener('mousemove', event => {
    const band = event.target.closest('.hover-band');
    if (!band) { hide(); return; }
    guide.setAttribute('x1', band.dataset.x);
    guide.setAttribute('x2', band.dataset.x);
    guide.setAttribute('visibility', 'visible');

    const head = document.createElement('b');
    head.textContent = band.dataset.hour;
    const lines = band.dataset.values.split('|').map((text, i) => {
      const line = document.createElement('div');
      const swatch = document.createElement('i');
      swatch.style.background = series[i][0];
      line.append(swatch, `${series[i][1]} : ${text}`);
      return line;
    });
    const days = band.dataset.days ? [Object.assign(document.createElement('small'), { textContent: band.dataset.days })] : [];
    tip.replaceChildren(head, ...lines, ...days);
    tip.hidden = false;

    // Beside the guide, on whichever side has room.
    const box = container.getBoundingClientRect();
    const at = band.getBoundingClientRect();
    const middle = at.left + at.width / 2 - box.left;
    const left = middle + 14 + tip.offsetWidth > box.width ? middle - 14 - tip.offsetWidth : middle + 14;
    tip.style.left = `${Math.max(0, left)}px`;
    tip.style.top = `${Math.max(0, event.clientY - box.top - tip.offsetHeight / 2)}px`;
  });
}


/* Two bars per month: what was paid for, and what was served.

   The point of the chart is the gap between them — the margin left to optimise.
   Grouped rather than overlaid: an overlay reads as a proportion of a whole and
   invites the eye to compare areas, where side by side both values keep their
   own baseline and the difference is the space between the two bars. */
export function monthlyPairs(months, series, label = '') {
  const width = 1040, height = 280, padLeft = 54, padRight = 16, padTop = 26, padBottom = 34;
  if (!months.length) return `<div class="msg">${esc(t().noData)}</div>`;

  const values = months.map(month => series.map(s => Number(month[s.key]) || 0));
  const peak = Math.max(1, ...values.flat());
  const plotWidth = width - padLeft - padRight, plotHeight = height - padTop - padBottom;
  const step = plotWidth / months.length;
  const barWidth = Math.min(22, (step * 0.62) / series.length);
  const y = v => padTop + plotHeight - (v / peak) * plotHeight;
  const axis = themeColor('--axis');

  const ticks = gridTicks([0, 0.5, 1], peak, y, padLeft, width - padRight, 11, v => nf.format(Math.round(v)));

  const bars = months.map((month, index) => {
    const groupWidth = barWidth * series.length + 3 * (series.length - 1);
    const left = padLeft + step * index + (step - groupWidth) / 2;
    const drawn = series.map((s, si) => {
      const v = Number(month[s.key]) || 0;
      const x = left + si * (barWidth + 3);
      // The value is written above the bar, not left to a tooltip: these charts
      // are read as screenshots, where hovering is not an option.
      return `<rect x="${x.toFixed(1)}" y="${y(v).toFixed(1)}" width="${barWidth.toFixed(1)}"
                    height="${Math.max(0, padTop + plotHeight - y(v)).toFixed(1)}" fill="${safeColor(s.color)}">
                <title>${esc(monthLabel(month.month, true))} — ${esc(s.label)} : ${nf.format(v)} h${month.coverage !== null && month.coverage !== undefined ? ` (${esc(t().capCoverageShort(month.coverage))})` : ''}</title></rect>
              <text x="${(x + barWidth / 2).toFixed(1)}" y="${(y(v) - 5).toFixed(1)}" text-anchor="middle"
                    font-size="10" fill="${safeColor(s.color)}">${nf.format(Math.round(v))}</text>`;
    }).join('');
    return drawn + `<text x="${(left + groupWidth / 2).toFixed(1)}" y="${height - padBottom + 16}"
                          text-anchor="middle" font-size="11" fill="${axis}">${esc(monthLabel(month.month))}${month.coverage !== null && month.coverage !== undefined ? ` (${month.coverage} %)` : ''}</text>`;
  }).join('');

  const legend = series.map((s, i) =>
    `<rect x="${padLeft + i * 190}" y="${height - 12}" width="11" height="11" fill="${safeColor(s.color)}"/>
     <text x="${padLeft + i * 190 + 18}" y="${height - 2}" font-size="12" fill="${axis}">${esc(s.label)}</text>`
  ).join('');

  return `<svg viewBox="0 0 ${width} ${height + 10}" width="100%" role="img" aria-label="${esc(label)}">${ticks}${bars}${legend}</svg>`;
}

/* ------------------------------------------------------------ shared pieces */

/* Horizontal grid lines, each with its value at the left of the plot. */
function gridTicks(ratios, peak, y, left, right, fontSize, label) {
  const grid = themeColor('--grid'), axis = themeColor('--axis');
  return ratios.map(ratio => {
    const v = peak * ratio;
    return `<line x1="${left}" x2="${right}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}" stroke="${grid}"/>
            <text x="${left - 8}" y="${(y(v) + 4).toFixed(1)}" text-anchor="end" font-size="${fontSize}" fill="${axis}">${label(v)}</text>`;
  }).join('');
}

/* The vertical line attachHover() moves to the hovered slot. */
function hoverGuide(top, plotHeight) {
  return `<line class="hover-guide" x1="0" x2="0" y1="${top}" y2="${top + plotHeight}"
                stroke="${themeColor('--axis')}" stroke-dasharray="3 3" visibility="hidden"/>`;
}

/* Colour and name of each series, for the hover box: "colour~name|…". */
function seriesAttribute(series) {
  return esc(series.map(s => `${safeColor(s.color)}~${s.label}`).join('|'));
}
