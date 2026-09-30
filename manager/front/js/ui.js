/* Small interface services: transient messages and clipboard. */

import { t } from './i18n.js';
import { esc, monthLabel } from './format.js';

let toastTimer = null;

/* tone 'ok' or 'err'. Long enough to read a call-id (1.4 s was not); a
   failure stays longer, it asks the reader to do something. */
export function toast(message, tone = 'ok') {
  const element = document.getElementById('toast');
  element.textContent = message;
  element.classList.toggle('err', tone === 'err');
  element.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { element.hidden = true; }, tone === 'err' ? 5000 : 3000);
}

/* Mark the buttons of a group as pressed or not, in class and in ARIA at once.
   The views keep their filters in module state across visits while their
   template is rebuilt each time: every group is drawn from that state through
   here, never left as the template had it. */
export function press(selector, isPressed) {
  for (const button of document.querySelectorAll(selector)) {
    const pressed = Boolean(isPressed(button));
    button.classList.toggle('on', pressed);
    button.setAttribute('aria-pressed', String(pressed));
  }
}

/* The months a period list offers: the current one and the 24 before, the
   selection kept across a redraw (a change of language redraws the labels). */
export function fillMonths(select, count = 24) {
  const now = new Date();
  const options = ['<option value="">—</option>'];
  for (let back = 0; back <= count; back++) {
    const date = new Date(now.getFullYear(), now.getMonth() - back, 1);
    const iso = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
    options.push(`<option value="${iso}">${esc(monthLabel(iso, true))}</option>`);
  }
  const selected = select.value;
  select.innerHTML = options.join('');
  select.value = selected;
}

/* A view's dialogs — never the shell's, which main.js wires once: ✕, Annuler
   (data-close) and a click on the backdrop close them. Scoped to the view:
   read from the whole document, the sign-out dialog got one more listener
   each time the Users view was opened. */
export function wireDialogs(view) {
  for (const dialog of view.querySelectorAll('dialog.modal')) {
    makeMovable(dialog);
    // A click closes from the backdrop only if it also began there: a text
    // selection dragged out of a field ends with its click on the dialog
    // itself, and closed the form being filled in.
    let pressedOnBackdrop = false;
    dialog.addEventListener('pointerdown', event => { pressedOnBackdrop = event.target === dialog; });
    dialog.addEventListener('click', event => {
      if (event.target.closest('[data-close]')) dialog.close();
      else if (event.target === dialog && pressedOnBackdrop) dialog.close();
      pressedOnBackdrop = false;
    });
  }
}

/* A dialog moves by its title bar, to uncover what lies under it — the rules
   already written, while adding one. It opens in the middle again each time.
   The offset is set through the CSSOM, which the CSP allows (a style
   attribute it would drop). The dialog stays whole on screen: pushed to an
   edge with only a strip showing, its close button and its fields were out
   of reach. */
function makeMovable(dialog) {
  const bar = dialog.querySelector(':scope > form > header');
  if (!bar) return;
  bar.classList.add('movable');
  let grab = null, x = 0, y = 0;
  bar.addEventListener('pointerdown', event => {
    if (event.button !== 0 || event.target.closest('button, a, input, select, textarea')) return;
    const box = dialog.getBoundingClientRect();
    // Where the dialog would sit without the offset: the clamp works on it.
    grab = { dx: event.clientX - x, dy: event.clientY - y,
             left: box.left - x, top: box.top - y, width: box.width, height: box.height };
    bar.setPointerCapture(event.pointerId);
    event.preventDefault();
  });
  bar.addEventListener('pointermove', event => {
    if (!grab) return;
    // Whole on screen; a dialog taller or wider than the window stays put on that axis.
    const clamp = (value, low, high) => (high < low ? 0 : Math.min(high, Math.max(low, value)));
    x = clamp(event.clientX - grab.dx, -grab.left, window.innerWidth - grab.left - grab.width);
    y = clamp(event.clientY - grab.dy, -grab.top, window.innerHeight - grab.top - grab.height);
    dialog.style.transform = `translate(${x}px, ${y}px)`;
  });
  const release = () => { grab = null; };
  bar.addEventListener('pointerup', release);
  bar.addEventListener('pointercancel', release);
  dialog.addEventListener('close', () => { x = 0; y = 0; dialog.style.transform = ''; });
}

/* On leaving a view: none of its dialogs stays open over the next one. */
export function closeDialogs(view) {
  for (const dialog of view ? view.querySelectorAll('dialog.modal') : []) {
    if (dialog.open) dialog.close();
  }
}

/* navigator.clipboard only exists in secure contexts (HTTPS / localhost);
   plain-HTTP deployments fall back to the legacy execCommand path. */
export async function copyText(text) {
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
    } else {
      const area = document.createElement('textarea');
      area.value = text;
      area.setAttribute('readonly', '');
      area.style.position = 'fixed';
      area.style.opacity = '0';
      document.body.appendChild(area);
      area.select();
      const copied = document.execCommand('copy');
      area.remove();
      if (!copied) throw new Error('execCommand');
    }
    toast(`${t().copied} : ${text}`);
  } catch {
    toast(t().copyFail, 'err');
  }
}

/* Delegated click-to-copy for any container holding .copy elements. */
export function enableCopy(container) {
  container.addEventListener('click', event => {
    const target = event.target.closest('.copy');
    if (target) copyText(target.dataset.copy);
  });
}
