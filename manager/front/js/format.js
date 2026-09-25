/* Formatting and escaping helpers shared by the views. */

import { lang, t } from './i18n.js';

export let nf = new Intl.NumberFormat('fr-FR');
export function refreshNumberFormat() {
  nf = new Intl.NumberFormat(lang() === 'fr' ? 'fr-FR' : 'en-GB');
}

export const esc = value => String(value).replace(/[&<>"']/g,
  c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/* Older proxies leak the literal string "None" for unset fields. */
export const norm = value => (value == null || value === '' || value === 'None') ? null : value;

export const dash = '<span class="dim">—</span>';
export const cell = value => value == null ? dash : esc(value);
export const copyable = (value, className = '') => value == null ? dash
  : `<span class="copy ${className}" data-copy="${esc(value)}">${esc(value)}</span>`;

/* The gateway field is the launcher address "host:port"; the port is fixed. */
export const hostOf = value => {
  const text = norm(value);
  return text == null ? null : text.replace(/:\d+$/, '');
};

const MONTHS = {
  fr: ['janv', 'févr', 'mars', 'avr', 'mai', 'juin', 'juil', 'août', 'sept', 'oct', 'nov', 'déc'],
  en: ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'],
};

export function monthLabel(iso, long = false) {
  const [year, month] = iso.split('-').map(Number);
  const name = (MONTHS[lang()] || MONTHS.fr)[month - 1];
  return long ? `${name} ${year}` : name;
}

/* A period label from the API: "YYYY-MM", "YYYY", a day, a range of days or
   "week of YYYY-MM-DD". The month and the week are said in the current
   language; the others read the same in both. */
export function periodLabel(label) {
  if (/^\d{4}-\d{2}$/.test(label)) return monthLabel(label, true);
  const week = /^week of (\d{4}-\d{2}-\d{2})$/.exec(label);
  return week ? t().weekOf(week[1]) : label;
}

/* Hours round to 0.0 for short calls, which reads as "nothing happened".
   Below an hour the report shows minutes instead. */
export function formatDuration(seconds) {
  if (!seconds) return '0';
  if (seconds < 3600) return `${Math.round(seconds / 60)} min`;
  return `${Math.round(seconds / 3600)} h`;
}

/* Seconds since an ISO 8601 instant, as hh:mm:ss. The gateway sends UTC. */
/** Seconds as hh:mm:ss. */
export function hms(seconds) {
  const whole = Math.max(0, Math.floor(seconds));
  const pad = n => String(n).padStart(2, '0');
  return `${pad(Math.floor(whole / 3600))}:${pad(Math.floor(whole % 3600 / 60))}:${pad(whole % 60)}`;
}

