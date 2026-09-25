/* Supervision view: live state of the registered gateways.
   Every view module exports mount() and unmount(); unmount must stop timers,
   otherwise a hidden view keeps polling the proxyAPI. */

import { get, errorMessage } from '../api.js';
import { t, translate, onLanguageChange } from '../i18n.js';
import { esc, norm, dash, copyable, hostOf, hms } from '../format.js';
import { enableCopy } from '../ui.js';
import { platformCell, attachIconFallback } from '../platforms.js';

const REFRESH_MS = 10000;

let data = null, refreshTimer = null, tickTimer = null, nextRefreshAt = 0;
let loadedAt = 0;
let interactUrl = '', stopListening = null, mounted = false, loading = false;

const $ = id => document.getElementById(id);

/* Text used by the search box: everything a human might paste from a log. */
const haystack = gateway =>
  [gateway.gw_id, gateway.ip, gateway.type, gateway.room, gateway.browsing,
   gateway.peer_uri, gateway.peer_name, gateway.pairing_code]
    .map(norm).filter(Boolean).join(' ').toLowerCase();

function render() {
  if (!data) return;
  const summary = data.summary;
  $('nTotal').textContent = summary.total;
  $('nFree').textContent = summary.free;
  $('nIdle').textContent = summary.idle;
  $('nIvr').textContent = summary.ivr;
  $('nCall').textContent = summary.in_call;

  const query = $('search').value.trim().toLowerCase();
  const all = data.gateways;
  const shown = query ? all.filter(gateway => haystack(gateway).includes(query)) : all;
  $('shown').textContent = all.length ? t().shown(shown.length, all.length) : '';

  if (!all.length) {
    $('rows').innerHTML = `<tr><td colspan="11" class="msg">${esc(t().empty)}</td></tr>`;
    return;
  }
  if (!shown.length) {
    $('rows').innerHTML = `<tr><td colspan="11" class="msg">${esc(t().noMatch)}</td></tr>`;
    return;
  }

  $('rows').innerHTML = shown.map(gateway => {
    const type = norm(gateway.type);
    // Seconds, not a timestamp: the proxy writes a naive local time and only
    // the server knows which clock it came from. What arrives here is already
    // resolved, and the tick below carries it forward between refreshes.
    const since = gateway.call_seconds;
    // Only a gateway on a call has anything to pilot, whether it sits in the
    // IVR or in a conference. Listing the states that do rather than those
    // that do not keeps a new state from silently getting the button.
    const control = ((gateway.state === 'call' || gateway.state === 'ivr') && interactUrl)
      ? `<a class="btn" href="${esc(interactUrl)}?gwId=${encodeURIComponent(gateway.gw_id)}" target="_blank" rel="noopener">${esc(t().control)}</a>`
      : '';
    // Searched by calling endpoint, not by Call-ID: the result may hold
    // several calls, hence a label and a tooltip distinct from the exact link.
    const trace = gateway.homer_url
      ? `<a class="btn" href="${esc(gateway.homer_url)}" target="_blank" rel="noopener" title="${esc(t().homerEndpointHint)}">${esc(t().homerEndpoint)}</a>`
      : '';
    return `<tr>
      <td><span class="id" title="${esc(gateway.gw_id)}">${copyable(gateway.gw_id, 'mono')}</span></td>
      <td>${type ? `<span class="type">${esc(t().types[type] || type)}</span>` : dash}</td>
      <td><span class="pill ${esc(gateway.state)}">${esc(t().states[gateway.state] || gateway.status || '?')}</span></td>
      <td>${copyable(norm(gateway.peer_name))}</td>
      <td>${copyable(norm(gateway.peer_uri), 'mono')}</td>
      <td>${copyable(norm(gateway.room), 'mono')}</td>
      <td>${platformCell(gateway.browsing, dash)}</td>
      <td class="num"${since === null || since === undefined ? '' : ` data-since="${Number(since)}"`}>${since === null || since === undefined
        ? dash : esc(hms(elapsed(since)))}</td>
      <td>${copyable(norm(gateway.pairing_code), 'mono')}</td>
      <td>${copyable(hostOf(gateway.ip), 'mono')}</td>
      <td class="actions"><div>${control}${trace}</div></td>
    </tr>`;
  }).join('');

  attachIconFallback($('rows'));
}

async function load() {
  // A reply slower than the period must not start a second poll under it.
  if (loading) return;
  loading = true;
  $('refresh').disabled = true;
  // Set before the request, not after it: the timer that calls this fires on
  // its own schedule, and counting from the reply left the countdown a second
  // or two ahead of the refresh it announced.
  nextRefreshAt = Date.now() + REFRESH_MS;
  loadedAt = Date.now();
  try {
    const fresh = await get('/api/gateways');
    // The view may have been replaced during the request (up to the proxy
    // timeout, 10 s): its elements are gone, and so is the reason to draw.
    if (!mounted) return;
    data = fresh;
    render();
  } catch (error) {
    if (!mounted) return;
    // Dropped, not kept: tick() re-renders `data` every second, and after a
    // reboot the last table it had — durations still counting — painted
    // over this message within the second. Stale rows are not a park.
    data = null;
    if (error.message !== 'unauthenticated') {
      $('rows').innerHTML = `<tr><td colspan="11" class="msg err">${esc(errorMessage(error, t()))}</td></tr>`;
    }
  } finally {
    loading = false;
    if (mounted) $('refresh').disabled = false;
  }
}

const elapsed = since => Number(since) + Math.floor((Date.now() - loadedAt) / 1000);

/* Every second, only the durations move. Redrawing the whole table did the
   same and more: the text being selected and the button holding the focus
   were replaced under the pointer and the keyboard, every second. */
function tick() {
  for (const cell of document.querySelectorAll('#rows td[data-since]')) {
    cell.textContent = hms(elapsed(cell.dataset.since));
  }
  $('countdown').textContent = nextRefreshAt
    ? t().countdown(Math.max(0, Math.ceil((nextRefreshAt - Date.now()) / 1000))) : '';
}

function applyLanguage() {
  // The view may have been replaced while its listener was still
  // registered: nothing to translate then.
  if (!mounted || !$('search')) return;
  translate(document);
  $('search').placeholder = t().search;
  for (const node of document.querySelectorAll('[data-tile]')) {
    node.textContent = t().tiles[node.dataset.tile];
  }
  $('parkHead').innerHTML = t().cols.map(column => `<th>${esc(column)}</th>`).join('');
  render();
  tick();
}

export function mount(context) {
  mounted = true;
  interactUrl = context.interactUrl || '';
  applyLanguage();
  stopListening = onLanguageChange(applyLanguage);
  $('refresh').addEventListener('click', load);
  $('search').addEventListener('input', render);
  enableCopy($('rows'));
  load();
  nextRefreshAt = Date.now() + REFRESH_MS;
  refreshTimer = setInterval(load, REFRESH_MS);
  tickTimer = setInterval(tick, 1000);
}

export function unmount() {
  mounted = false;
  clearInterval(refreshTimer);
  clearInterval(tickTimer);
  nextRefreshAt = 0;
  data = null;
  if (stopListening) stopListening();
  stopListening = null;
}
