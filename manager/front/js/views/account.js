/* My account: change my password. An account that comes from the identity
   provider has no password here and sees a note instead. */

import { t, translate, onLanguageChange } from '../i18n.js';
import { toast } from '../ui.js';
import { wirePasswordForm } from '../password.js';

let stopListening = null, unwire = null, mounted = false;
const $ = id => document.getElementById(id);

function applyLanguage(context) {
  if (!mounted || !$('accountForm')) return;
  translate(document);
  $('accountSub').textContent = t().accountSub(context.user, t().roles[context.role] || context.role);
  $('pwdRule').textContent = t().pwdRule(context.minLength);
}

export function mount(context) {
  $('accountUser').value = context.user;
  mounted = true;
  const local = context.source !== 'proconnect';
  $('accountPasswordPanel').hidden = !local;
  $('accountSsoPanel').hidden = local;
  applyLanguage(context);
  stopListening = onLanguageChange(() => applyLanguage(context));
  if (local) {
    unwire = wirePasswordForm(
      { form: 'accountForm', current: 'accountCurrent', next: 'accountNext', confirm: 'accountConfirm',
        error: 'accountError', button: 'accountSave' },
      { minLength: context.minLength, username: context.user },
      () => toast(t().pwdChanged));
  }
}

export function unmount() {
  mounted = false;
  if (unwire) unwire();
  unwire = null;
  if (stopListening) stopListening();
  stopListening = null;
}
