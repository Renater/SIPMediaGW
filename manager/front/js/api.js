/* HTTP access to the Manager API.
   The browser holds no token: it authenticates once with a session cookie and
   the Manager relays the proxyAPI with the admin token kept server-side. */

let unauthenticatedHandler = () => {};
let passwordRequiredHandler = () => {};

export function onUnauthenticated(handler) {
  unauthenticatedHandler = handler;
}

/* The server refuses every route but the password change with this 403
   while an account must change its password: the shell shows that form. */
export function onPasswordRequired(handler) {
  passwordRequiredHandler = handler;
}

const PASSWORD_REQUIRED = 'password change required';

export async function get(path) {
  const response = await fetch(path, { headers: { Accept: 'application/json' } });
  if (response.status === 401) {
    unauthenticatedHandler();
    throw new Error('unauthenticated');
  }
  if (!response.ok) {
    const detail = (await response.json().catch(() => ({}))).detail || `HTTP ${response.status}`;
    if (response.status === 403 && detail === PASSWORD_REQUIRED) passwordRequiredHandler();
    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }
  return response.json();
}

/* User-facing message for a failed call: translated by status, never the raw
   server text (the API speaks English, the screen speaks the user's language). */
export function errorMessage(error, t) {
  if (error.status === 503) return t.serviceUnavailable;
  if (error.status === 404) return t.notFound;
  return t.requestFailed;
}

/* Several reads side by side. A failing route blanks its own section, never
   the whole view — except a lost session, which ends it: that one is thrown.
   `strings` is the translation getter, read when a failure is shown. */
export async function settleAll(requests, strings) {
  const settled = await Promise.allSettled(requests);
  const denied = settled.find(r => r.status === 'rejected' && r.reason.message === 'unauthenticated');
  if (denied) throw denied.reason;
  return {
    value: i => settled[i].status === 'fulfilled' ? settled[i].value : null,
    failure: i => settled[i].status === 'rejected' ? errorMessage(settled[i].reason, strings()) : null,
  };
}

export async function post(path, body) {
  return send('POST', path, body);
}

export async function put(path, body) {
  return send('PUT', path, body);
}

export async function del(path) {
  return send('DELETE', path);
}

/* One writer for the three verbs: they differ only by method, and three copies
   of the same six lines is how one of them ends up drifting. Like post, these
   return { ok, data } rather than throwing — a rejected write is an answer the
   caller has to show, not an exception. */
async function send(method, path, body) {
  const response = await fetch(path, {
    method,
    headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const data = await response.json().catch(() => ({}));
  return { ok: response.ok, status: response.status, data };
}

/* Fragment loader for the view templates under front/views/. */
export async function html(path) {
  // Cache-Control: no-cache from the server makes the browser revalidate the
  // fragment (304 when unchanged), so a template never outlives its module.
  const response = await fetch(path);
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  return response.text();
}
