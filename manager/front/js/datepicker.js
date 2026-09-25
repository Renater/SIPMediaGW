/* Calendar popover of the call log and the audit log: a range of days over
   two months, a first day then a last.

   Days are integers YYYYMMDD in local time. Comparing two days is comparing two
   numbers, and no arithmetic on milliseconds can slip an hour across a change
   of daylight saving time. The panel is rebuilt from its state on every change;
   the hover preview of a range only repaints the cells.

   Keyboard (the grid pattern of the WAI-ARIA practices, as the RGAA expects):
   arrows move by a day or a week, Page Up / Page Down by a month, Home / End
   to the ends of the week, Enter or Space picks, Escape closes and gives focus
   back to the field that opened the panel. */

import { t, lang } from './i18n.js';
import { esc } from './format.js';

export const pad = n => String(n).padStart(2, '0');
export const keyOf = date => date.getFullYear() * 10000 + (date.getMonth() + 1) * 100 + date.getDate();
export const dateOf = key => new Date(Math.floor(key / 10000), Math.floor(key / 100) % 100 - 1, key % 100);
export const isoOf = key => { const d = dateOf(key); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; };
export const shortDate = key => { const d = dateOf(key); return `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()}`; };
export const addDays = (key, n) => { const d = dateOf(key); return keyOf(new Date(d.getFullYear(), d.getMonth(), d.getDate() + n)); };
export const todayKey = () => keyOf(new Date());

/* A month is counted as year * 12 + month, so "the next one" is + 1. */
const monthOf = key => Math.floor(key / 10000) * 12 + Math.floor(key / 100) % 100 - 1;
const firstOf = month => keyOf(new Date(Math.floor(month / 12), month % 12, 1));

function addMonths(key, n) {
  const d = dateOf(key);
  const last = new Date(d.getFullYear(), d.getMonth() + n + 1, 0).getDate();
  return keyOf(new Date(d.getFullYear(), d.getMonth() + n, Math.min(d.getDate(), last)));
}

const locale = () => (lang() === 'fr' ? 'fr-FR' : 'en-GB');
const capitalise = text => text.charAt(0).toUpperCase() + text.slice(1);
const monthTitle = month =>
  capitalise(new Intl.DateTimeFormat(locale(), { month: 'long', year: 'numeric' }).format(dateOf(firstOf(month))));
const longDate = key =>
  new Intl.DateTimeFormat(locale(), { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' }).format(dateOf(key));

/* Monday first: 2024-01-01 was a Monday. */
function weekdays() {
  const narrow = new Intl.DateTimeFormat(locale(), { weekday: 'narrow' });
  const long = new Intl.DateTimeFormat(locale(), { weekday: 'long' });
  return Array.from({ length: 7 }, (_, i) => {
    const day = new Date(2024, 0, 1 + i);
    return { narrow: narrow.format(day), long: long.format(day) };
  });
}

const CHEVRON = {
  prev: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M15 6l-6 6 6 6"/></svg>',
  next: '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 6l6 6-6 6"/></svg>',
};

/**
 * panel: the empty element that becomes the popover (hidden until opened).
 * max: the last day that can be picked, or null.
 * onApply: called with { start, end }.
 */
/* The two date fields of a window open the calendar on their end of it; a
   second click on the field that opened it closes it. `getRange` returns the
   window as it is now: views replace it rather than mutate it. */
export function openFromFields(calendar, getRange, fields) {
  for (const [element, picking] of fields) {
    element.addEventListener('click', () => {
      if (calendar.isOpen() && calendar.openedBy() === element) calendar.close(true);
      else calendar.open({ start: getRange().start, end: getRange().end, picking, from: element });
    });
  }
}

export function createCalendar({ panel, max = null, onApply }) {
  let state = null;          // null while closed
  let opener = null;
  let wantFocus = false;

  const limit = key => max != null && key > max;
  const blocked = key => limit(key) || (state.picking === 'end' && key < state.start);
  const visible = () => [state.view, state.view + 1];

  /* Keep `key` on screen: the left month moves only as far as needed. */
  function reveal(key) {
    const month = monthOf(key), shown = visible();
    if (month < shown[0]) state.view = month;
    if (month > shown[shown.length - 1]) state.view = month - (shown.length - 1);
  }

  /* The right-hand month never goes past the one holding `max`. */
  const lastView = () => (max == null ? Infinity : monthOf(max) - 1);

  function hint() {
    return state.picking === 'start' ? t().calPickStart : t().calPickEnd;
  }

  function dayCell(key, month) {
    if (monthOf(key) !== month) return '<td></td>';
    const d = dateOf(key);
    const edge = key === state.start || key === state.end;
    const disabled = blocked(key);
    let label = longDate(key);
    if (key === state.start) label += `, ${t().calStartMark}`;
    if (key === state.end) label += `, ${t().calEndMark}`;
    if (disabled) label += `, ${t().calUnavailable}`;
    return `<td><button type="button" class="cal-day" data-day="${key}" tabindex="${key === state.focus ? 0 : -1}"`
      + ` aria-label="${esc(label)}" aria-pressed="${edge}"${disabled ? ' aria-disabled="true"' : ''}`
      + `${key === todayKey() ? ' data-today="true"' : ''}>${d.getDate()}</button></td>`;
  }

  function monthGrid(month) {
    const first = firstOf(month);
    const offset = (dateOf(first).getDay() + 6) % 7;
    const origin = addDays(first, -offset);
    const id = `${panel.id}-m${month}`;
    const rows = [];
    for (let week = 0; week < 6; week++) {
      const cells = [];
      for (let day = 0; day < 7; day++) cells.push(dayCell(addDays(origin, week * 7 + day), month));
      rows.push(`<tr>${cells.join('')}</tr>`);
    }
    const heads = weekdays().map(w => `<th scope="col" abbr="${esc(w.long)}">${esc(w.narrow)}</th>`).join('');
    return `<section class="cal-month">
      <h3 class="cal-title" id="${esc(id)}">${esc(monthTitle(month))}</h3>
      <table class="cal-grid" role="grid" aria-labelledby="${esc(id)}">
        <thead><tr>${heads}</tr></thead><tbody>${rows.join('')}</tbody>
      </table></section>`;
  }

  function footer() {
    const days = Math.round((dateOf(state.end) - dateOf(state.start)) / 86400000) + 1;
    return `<p class="cal-summary">${esc(t().calSummary(shortDate(state.start), shortDate(state.end), days))}</p>
      <button type="button" data-action="cancel">${esc(t().calCancel)}</button>
      <button type="button" class="cal-apply" data-action="apply">${esc(t().calApply)}</button>`;
  }

  /* The band between the first and last day, drawn on the cells so that a
     hover can move it without rebuilding the grid. */
  function paint(hover = null) {
    const end = hover != null && state.picking === 'end' ? Math.max(hover, state.start) : state.end;
    panel.classList.toggle('previewing', hover != null && state.picking === 'end');
    for (const button of panel.querySelectorAll('.cal-day')) {
      const key = Number(button.dataset.day);
      const cell = button.parentElement;
      let band = '';
      if (end > state.start) {
        if (key === state.start) band = 'start';
        else if (key === end) band = 'end';
        else if (key > state.start && key < end) band = 'mid';
      }
      if (band) cell.dataset.band = band; else delete cell.dataset.band;
    }
  }

  function render() {
    const shown = visible();
    const atEnd = shown[0] >= lastView();
    // nosemgrep: mgr-innerhtml-unescaped -- every value below goes through esc() (checked with poisoned data, tests/e2e/escaping.mjs)
    panel.innerHTML = `<p class="cal-hint" aria-live="polite">${esc(hint())}</p>
      <div class="cal-body">
        <button type="button" class="cal-nav" data-nav="-1" aria-label="${esc(t().calPrevMonth)}">${CHEVRON.prev}</button>
        <div class="cal-months">${shown.map(monthGrid).join('')}</div>
        <button type="button" class="cal-nav" data-nav="1" aria-label="${esc(t().calNextMonth)}"${atEnd ? ' disabled' : ''}>${CHEVRON.next}</button>
      </div>
      <div class="cal-foot">${footer()}</div>`;
    panel.setAttribute('aria-label', t().calDialogRange);
    paint();
    if (wantFocus) {
      wantFocus = false;
      const target = panel.querySelector(`[data-day="${state.focus}"]`);
      if (target) target.focus();
    }
  }

  function pick(key) {
    if (blocked(key)) return;
    if (state.picking === 'start') {
      // The end follows the start: kept when it is still after it.
      state.start = key;
      if (state.end < key) state.end = key;
      state.picking = 'end';
    } else {
      state.end = key;
      state.picking = 'start';
    }
    state.focus = key;
    wantFocus = true;
    render();
  }

  function moveFocus(key) {
    // Past `max` there is nothing to reach: the focus stops on the last day.
    state.focus = limit(key) ? max : key;
    reveal(state.focus);
    wantFocus = true;
    render();
  }

  function onClick(event) {
    // Attached for the life of the panel: a closed panel still receives
    // events (a mouseover when its content changes under the pointer).
    if (!state) return;
    const day = event.target.closest('[data-day]');
    if (day) { pick(Number(day.dataset.day)); return; }
    const nav = event.target.closest('[data-nav]');
    if (nav && !nav.disabled) {
      state.view = Math.min(state.view + Number(nav.dataset.nav), Math.max(state.view, lastView()));
      state.focus = firstOf(state.view);
      render();
      return;
    }
    const action = event.target.closest('[data-action]');
    if (!action) return;
    const name = action.dataset.action;
    if (name === 'cancel') close(true);
    if (name === 'apply') {
      const chosen = { start: state.start, end: state.end };
      close(true);
      onApply(chosen);
    }
  }

  const MOVES = {
    ArrowLeft: key => addDays(key, -1), ArrowRight: key => addDays(key, 1),
    ArrowUp: key => addDays(key, -7), ArrowDown: key => addDays(key, 7),
    PageUp: key => addMonths(key, -1), PageDown: key => addMonths(key, 1),
    Home: key => addDays(key, -((dateOf(key).getDay() + 6) % 7)),
    End: key => addDays(key, 6 - ((dateOf(key).getDay() + 6) % 7)),
  };

  function onKeydown(event) {
    // Attached for the life of the panel: a closed panel still receives
    // events (a mouseover when its content changes under the pointer).
    if (!state) return;
    if (event.key === 'Escape') {
      event.stopPropagation();
      close(true);
      return;
    }
    const day = event.target.closest('[data-day]');
    const move = MOVES[event.key];
    if (!day || !move) return;
    event.preventDefault();
    moveFocus(move(Number(day.dataset.day)));
  }

  function onHover(event) {
    // Attached for the life of the panel: a closed panel still receives
    // events (a mouseover when its content changes under the pointer).
    if (!state) return;
    const day = event.target.closest('[data-day]');
    if (state.picking !== 'end') return;
    paint(day && !blocked(Number(day.dataset.day)) ? Number(day.dataset.day) : null);
  }

  /* A click anywhere else closes the panel without applying. The field that
     opened it is left out: its own handler decides (it may switch from the
     first day to the last). The event's path is read, not panel.contains():
     a click on a day re-renders the panel, and by the time the click reaches
     document the button it landed on is no longer in it. */
  function onOutside(event) {
    const path = event.composedPath();
    if (path.includes(panel) || (opener && path.includes(opener))) return;
    close(false);
  }

  function open({ start, end = start, picking = 'start', from }) {
    const focus = picking === 'end' ? end : start;
    state = { start, end, picking, focus, view: 0 };
    state.view = monthOf(start);
    // Two months: the start on the left, unless that would put a month past
    // `max` on the right.
    state.view = Math.min(state.view, lastView());
    reveal(focus);
    if (opener && opener !== from) opener.setAttribute('aria-expanded', 'false');
    opener = from || null;
    if (opener) opener.setAttribute('aria-expanded', 'true');
    panel.hidden = false;
    wantFocus = true;
    render();
    document.addEventListener('click', onOutside);
  }

  function close(restoreFocus = false) {
    if (!state) return;
    state = null;
    panel.hidden = true;
    panel.innerHTML = '';
    document.removeEventListener('click', onOutside);
    if (opener) {
      opener.setAttribute('aria-expanded', 'false');
      if (restoreFocus && document.contains(opener)) opener.focus();
    }
    opener = null;
  }

  panel.addEventListener('click', onClick);
  panel.addEventListener('keydown', onKeydown);
  panel.addEventListener('mouseover', onHover);
  panel.addEventListener('mouseleave', () => { if (state) paint(); });

  return {
    open,
    close,
    isOpen: () => state != null,
    openedBy: () => opener,
    /* Language change: same state, new words. */
    refresh: () => { if (state) render(); },
    /* Unmount: the document listener must not outlive the view. */
    destroy: () => { close(false); },
  };
}
