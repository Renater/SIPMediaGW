/* A JSON value as a tree that folds: the payload a gateway pushed, read in the
   call drawer. Built with createElement and textContent only — the payload is
   the gateway's text, never markup — and indented through the CSSOM, which
   the CSP allows (a style attribute it would drop).

   Only what is open is in the DOM, and a long array shows its first
   PAGE items with a button for the next ones: a day of media samples is
   thousands of objects, and drawing them all froze the tab. */

import { t } from './i18n.js';
import { nf } from './format.js';

const PAGE = 200;          // items drawn per array or object before "show more"
const OPENED_MATCHES = 100; // matches whose ancestors a search opens
const INDENT = 18;         // px per level

const isContainer = value => value !== null && typeof value === 'object';
const keyOf = path => JSON.stringify(path);

export function createJsonTree(host, { onMatches } = {}) {
  let root = null;
  let open = new Set();       // paths (keyOf) of the open containers
  let shown = new Map();      // path -> number of children drawn
  let needle = '';

  function el(tag, { cls, text } = {}) {
    const node = document.createElement(tag);
    if (cls) node.classList.add(cls);
    if (text !== undefined) node.textContent = text;
    return node;
  }

  // The text, with the part matching the search marked.
  function marked(text, { cls }) {
    const span = el('span', { cls });
    const at = needle ? text.toLowerCase().indexOf(needle) : -1;
    if (at < 0) {
      span.textContent = text;
      return span;
    }
    span.append(text.slice(0, at), el('mark', { cls: 'jt-hit', text: text.slice(at, at + needle.length) }),
      text.slice(at + needle.length));
    return span;
  }

  function scalar(value) {
    if (typeof value === 'string') return marked(JSON.stringify(value), { cls: 'jt-str' });
    if (typeof value === 'number') return marked(String(value), { cls: 'jt-num' });
    return marked(String(value), { cls: 'jt-lit' });   // true, false, null
  }

  function row(depth) {
    const line = el('div', { cls: 'jt-row' });
    line.style.paddingLeft = `${depth * INDENT + 22}px`;
    return line;
  }

  function label(line, name) {
    if (name === undefined) return;
    if (typeof name === 'number') line.append(el('span', { cls: 'jt-index', text: `${name}: ` }));
    else line.append(marked(JSON.stringify(name), { cls: 'jt-key' }), el('span', { cls: 'jt-punct', text: ': ' }));
  }

  function draw(out, value, path, name, depth, last) {
    const comma = last ? '' : ',';
    if (!isContainer(value)) {
      const line = row(depth);
      label(line, name);
      line.append(scalar(value), el('span', { cls: 'jt-punct', text: comma }));
      out.push(line);
      return;
    }
    const array = Array.isArray(value);
    const entries = array ? value.map((item, index) => [index, item]) : Object.entries(value);
    const [left, right] = array ? ['[', ']'] : ['{', '}'];
    const id = keyOf(path);
    const isOpen = open.has(id) && entries.length > 0;
    const line = row(depth);
    const toggle = el('button', { cls: 'jt-toggle', text: isOpen ? '▾' : '▸' });
    toggle.type = 'button';
    toggle.dataset.path = id;
    toggle.setAttribute('aria-expanded', String(isOpen));
    toggle.setAttribute('aria-label', name === undefined ? '$' : String(name));
    toggle.disabled = entries.length === 0;
    line.append(toggle);
    label(line, name);
    if (!isOpen) {
      const count = array ? t().jsonItems(entries.length) : t().jsonKeys(entries.length);
      line.append(el('span', { cls: 'jt-punct', text: entries.length ? `${left} … ${right}` : `${left}${right}` }),
        el('span', { cls: 'jt-punct', text: comma }), el('span', { cls: 'jt-sum', text: count }));
      out.push(line);
      return;
    }
    line.append(el('span', { cls: 'jt-punct', text: left }));
    out.push(line);
    const limit = Math.min(entries.length, shown.get(id) || PAGE);
    for (let index = 0; index < limit; index++) {
      const [childName, child] = entries[index];
      draw(out, child, [...path, childName], childName, depth + 1, index === entries.length - 1);
    }
    if (limit < entries.length) {
      const more = row(depth + 1);
      const button = el('button', { cls: 'jt-more', text: t().jsonMore(nf.format(Math.min(PAGE, entries.length - limit)),
        nf.format(entries.length - limit)) });
      button.type = 'button';
      button.dataset.more = id;
      button.dataset.limit = String(limit);
      more.append(button);
      out.push(more);
    }
    const close = row(depth);
    close.append(el('span', { cls: 'jt-punct', text: right + comma }));
    out.push(close);
  }

  function render() {
    const scroll = host.scrollTop;
    const out = [];
    if (root !== null) draw(out, root, [], undefined, 0, true);
    host.replaceChildren(...out);
    host.scrollTop = scroll;
  }

  // Every container path down to `depth` levels under the root.
  function openTo(depth) {
    const found = new Set();
    (function walk(value, path) {
      if (!isContainer(value) || path.length > depth) return;
      found.add(keyOf(path));
      for (const [name, child] of Array.isArray(value) ? value.entries() : Object.entries(value)) {
        walk(child, [...path, name]);
      }
    })(root, []);
    return found;
  }

  function search(text) {
    needle = text.trim().toLowerCase();
    if (!needle) {
      onMatches?.(null);
      render();
      return;
    }
    let count = 0;
    (function walk(value, path, name) {
      const hit = (typeof name === 'string' && JSON.stringify(name).toLowerCase().includes(needle)) ||
        (!isContainer(value) && (typeof value === 'string' ? JSON.stringify(value) : String(value))
          .toLowerCase().includes(needle));
      if (hit) {
        count++;
        // Open the way down to it — the first matches only, or a search for
        // "0" in a day of samples would open everything.
        if (count <= OPENED_MATCHES) {
          for (let depth = 0; depth < path.length; depth++) {
            const parent = keyOf(path.slice(0, depth));
            open.add(parent);
            const index = path[depth];
            if (typeof index === 'number' && index >= (shown.get(parent) || PAGE)) shown.set(parent, index + 1);
          }
        }
      }
      if (!isContainer(value)) return;
      for (const [childName, child] of Array.isArray(value) ? value.entries() : Object.entries(value)) {
        walk(child, [...path, childName], childName);
      }
    })(root, [], undefined);
    onMatches?.(count, OPENED_MATCHES);
    render();
    host.querySelector('.jt-hit')?.scrollIntoView({ block: 'center' });
  }

  host.addEventListener('click', event => {
    const toggle = event.target.closest('button.jt-toggle');
    if (toggle) {
      if (open.has(toggle.dataset.path)) open.delete(toggle.dataset.path);
      else open.add(toggle.dataset.path);
      render();
      host.querySelector(`button.jt-toggle[data-path="${CSS.escape(toggle.dataset.path)}"]`)?.focus();
      return;
    }
    const more = event.target.closest('button.jt-more');
    if (more) {
      shown.set(more.dataset.more, Number(more.dataset.limit) + PAGE);
      render();
    }
  });

  return {
    show(value, depth = 2) {
      root = value === undefined ? null : value;
      shown = new Map();
      needle = '';
      open = openTo(depth);
      host.scrollTop = 0;
      render();
    },
    levels(depth) { open = openTo(depth); render(); },
    expandAll() { open = openTo(Infinity); render(); },
    collapseAll() { open = new Set([keyOf([])]); render(); },   // the root stays open
    search,
    clear() { root = null; open = new Set(); shown = new Map(); host.replaceChildren(); },
  };
}
