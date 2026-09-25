/* The "change my password" form: the current one, the new one twice.

   Used twice — on the sign-in page when an account must change its password
   before doing anything else, and in the account view — so the checks and
   the wording live here once. The server checks everything again; these are
   the same rules, applied before a round trip. */

import { post } from './api.js';
import { t } from './i18n.js';

/* A message key for what is wrong with the form, or null. */
export function localProblem({ current, next, confirm, minLength, username }) {
  if (!current) return 'pwdNeedCurrent';
  if (next.length < minLength) return 'pwdTooShort';
  if (next !== confirm) return 'pwdMismatch';
  if (next === current) return 'pwdSameAsCurrent';
  if (username && next.toLowerCase() === username.toLowerCase()) return 'pwdIsUsername';
  return null;
}

/* Server messages are English; the ones a person meets are translated by
   their meaning, the rest fall back to a generic line. */
export function serverMessage(status, detail) {
  if (status === 403) return t().pwdWrongCurrent;
  if (status === 429) return t().loginThrottled;
  if (/at least/.test(detail)) return t().pwdTooShort(minLengthOf(detail));
  if (/differ from the username/.test(detail)) return t().pwdIsUsername;
  if (/default password/.test(detail)) return t().pwdIsDefault;
  if (/current one/.test(detail)) return t().pwdSameAsCurrent;
  if (/two new passwords/.test(detail)) return t().pwdMismatch;
  return t().pwdFailed;
}

const minLengthOf = detail => Number((/(\d+)/.exec(detail) || [])[1]) || 0;

/**
 * Wire a form. ids: { form, current, next, confirm, error, button }.
 * context: { minLength, username }. onSuccess: called once the server said yes.
 */
export function wirePasswordForm(ids, context, onSuccess) {
  const $ = id => document.getElementById(id);
  const say = message => { $(ids.error).textContent = message; };
  const handler = async event => {
    event.preventDefault();
    say('');
    const values = { current: $(ids.current).value, next: $(ids.next).value, confirm: $(ids.confirm).value };
    const problem = localProblem({ ...values, minLength: context.minLength, username: context.username });
    if (problem) {
      say(problem === 'pwdTooShort' ? t().pwdTooShort(context.minLength) : t()[problem]);
      return;
    }
    $(ids.button).disabled = true;
    try {
      const { ok, status, data } = await post('/api/account/password',
        { current: values.current, new: values.next, confirm: values.confirm });
      if (!ok) { say(serverMessage(status, data.detail || '')); return; }
      for (const id of [ids.current, ids.next, ids.confirm]) $(id).value = '';
      onSuccess();
    } finally {
      $(ids.button).disabled = false;
    }
  };
  $(ids.form).addEventListener('submit', handler);
  return () => $(ids.form).removeEventListener('submit', handler);
}
