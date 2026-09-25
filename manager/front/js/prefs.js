/* Display preferences, remembered across sessions. Never a secret. */

const KEY = 'gwmanager.prefs';

export function loadPrefs() {
  try { return JSON.parse(localStorage.getItem(KEY)) || {}; } catch { return {}; }
}

export function savePrefs(patch) {
  try { localStorage.setItem(KEY, JSON.stringify({ ...loadPrefs(), ...patch })); }
  catch { /* private browsing: preferences simply do not persist */ }
}
