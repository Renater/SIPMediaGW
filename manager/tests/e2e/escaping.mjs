/*
 * Every screen of the console fed poisoned data: each text field of each API
 * answer carries markup that breaks out of text and of both kinds of
 * attribute. The page must show it as text — no element may be created from it.
 *
 *   npm install playwright   (once, anywhere)
 *   node tests/e2e/escaping.mjs [front directory]      # default: ./front
 *
 * Exit status 1 when anything was injected. Not part of ./tools/test.sh: the
 * test image carries Node for `node --check`, not a browser.
 * Last run: 0 injected over the 9 views, the drawer, the charts' tooltips
 * and the dialogs.
 */
/* global process */   // a Node script, not a page of the console
import { chromium } from 'playwright';
import fs from 'fs'; import path from 'path';
const FRONT = process.argv[2] || path.join(process.cwd(), 'front');
const types = { '.js': 'text/javascript', '.css': 'text/css', '.html': 'text/html', '.svg': 'image/svg+xml', '.png': 'image/png' };
// Breaks out of text, double-quoted and single-quoted attributes alike.
const P = tag => `"'><img src=x data-xss="${tag}"><svg data-xss="${tag}">`;
const now = new Date().toISOString();
const call = id => ({ id, call_id: P('call_id'), call_start: now, call_end: now, outcome: 'completed', duration_s: 60, occupancy_s: 70,
  close_reason: P('close_reason'), last_event_type: P('last_event'), source_name: P('source_name'), peer_display_name: P('pdn'),
  source_uri: P('source_uri'), source_number: P('source_number'), source_domain: P('source_domain'), org_unit: P('org_unit'),
  destination_uri: P('dest_uri'), destination_domain: P('dest_domain'), platform: P('platform'), room: P('room'), main_app: P('main_app'),
  gw_alias: P('gw_alias'), gw_host: P('gw_host'), received_at: now, terminal: P('terminal'), video_state: P('video_state'),
  peer_user_agent: P('ua'), audio_codec: P('acodec'), video_codec: P('vcodec'), video_encoder: P('venc'),
  media_direction: { audio: P('adir'), video: P('vdir') }, gw_version: P('gwv'), baresip_version: P('bv'), baresip_patch: P('bp'),
  chromium_version: P('cv'), video_min_rx_fps: 3, video_low_intervals: P('low'), video_keyframe_requests: P('kf'), presentation_s: 5,
  frame_rates: [{ t: 0, seconds: 5, rx: 10, tx: 10, presentation: true }, { t: 5, seconds: 5, rx: 12, tx: 11 }],
  media: [{ media: P('media'), stream_index: P('si'), direction: P('mdir'), packets: 1, lost_packets: 0, jitter_ms: 1, avg_bitrate_kbps: 1 }],
  dtmf_events: [{ input: P('dtmf') }], homer_url: 'https://homer.example/x?q="><img src=x data-xss="homer">', homer_link_kind: 'room',
  raw: { evil: P('raw') } });
const API = {
  '/api/me': { authenticated: true, role: 'admin', user: P('me') },
  '/api/gateways': { summary: { total: 1, in_call: 1, ivr: 0, idle: 0, free: 0 }, gateways: [{ gw_id: P('gw_id'), type: P('type'), state: 'call',
    status: P('status'), peer_name: P('peer_name'), peer_uri: P('peer_uri'), room: P('groom'), browsing: P('browsing'), call_seconds: 5,
    pairing_code: P('pairing'), ip: P('ip'), homer_url: 'https://homer.example/?"><img src=x data-xss="ghomer">' }] },
  '/api/reporting/summary': { label: P('label'), calls: 3, seconds: 100, peak_concurrent: 2 },
  '/api/reporting/org-units': [{ org_unit: P('ru_unit'), calls: 3, hours: 1 }],
  '/api/reporting/platforms': [{ platform: P('rplat'), calls: 3, hours: 1 }, { platform: 'teams', calls: 1, hours: 1 }],
  '/api/reporting/monthly': { months: [{ month: '2026-08', calls: 3, hours: 1 }, { month: '2026-09', calls: 4, hours: 2 }], trend_hours: [1, 2] },
  '/api/reporting/outcomes': { label: P('qlabel'), outcomes: [{ outcome: P('qoutcome'), sessions: 3, gateway_hours: 1 }] },
  '/api/reporting/ivr-reasons': [{ close_reason: P('qreason'), outcome: P('qro'), is_failure: false, sessions: 1, pct: 10, avg_occupancy_s: 5 }],
  '/api/reporting/video-states': { states: [{ video_state: P('qvs'), sessions: 1 }] },
  '/api/reporting/pool-profile': { label: P('plabel'), profile: [{ day_type: 'weekday', hour: 9, busy_peak: 2, p: 1 }], previous: [] },
  '/api/reporting/pool-pressure': { slots: [{ day_type: P('pday'), hour: P('phour'), no_spare_minutes: 5, cold_start_minutes: 1, no_spare_pct: 3 }] },
  '/api/reporting/pool-hours': [{ month: '2026-09', provisioned_hours: 5, call_hours: 3, coverage_pct: P('cov') }],
  '/api/reporting/concurrency/hourly': [{ hour: 9, median: 1, p95: 2, peak: 3, days: 2 }],
  '/api/reporting/pool-period-hours': { provisioned_hours: 5, call_hours: 3, coverage_pct: 50 },
  '/api/reporting/calls': { total: 1, calls: [call(7)] },
  '/api/reporting/calls/7': call(7),
  '/api/users': [{ username: P('uname'), first_name: P('ufirst'), last_name: P('ulast'), role: P('urole'), source: P('usource'),
    enabled: true, must_change_password: false, last_login_at: now, email: P('umail') }],
  '/api/org-units': { units: [{ code: P('ucode'), label: P('ulabel'), active: true, rules: 1, calls: 1 }],
    rules: [{ id: 1, org_unit_code: P('rcode'), field: P('rfield'), match_type: P('rmatch'), pattern: P('rpattern'), description: P('rdesc'), active: true, position: 1 }],
    unassigned: 1 },
  '/api/audit': { total: 2, lines: [
    { type: 'user', at: now, actor: P('actor'), action: P('uaction'), target: P('utarget'), detail: { first_name: P('dfirst'), role: P('drole') } },
    { type: 'org_unit', at: now, actor: P('actor2'), action: P('oaction'), target: 'rule 1', detail: { after: { field: P('af'), match_type: P('am'), pattern: P('ap'), org_unit_code: P('ac') } } },
    { type: 'org_unit', at: now, actor: 'x', action: 'update', target: P('ot'), detail: { after: { code: P('oc'), label: P('ol'), active: false } } }] },
};
const b = await chromium.launch();
const p = await (await b.newContext({ locale: 'fr-FR', viewport: { width: 1400, height: 900 } })).newPage();
const errors = [], dialogs = [];
p.on('pageerror', e => errors.push(String(e))); p.on('dialog', d => { dialogs.push(d.message()); d.dismiss(); });
await p.route('http://app.test/**', async route => {
  const url = new URL(route.request().url());
  if (url.pathname === '/') return route.fulfill({ body: fs.readFileSync(path.join(FRONT, 'index.html')), contentType: 'text/html' });
  if (url.pathname.startsWith('/static/')) { const f = path.join(FRONT, url.pathname.slice(8)); if (!fs.existsSync(f)) return route.fulfill({ status: 404 }); return route.fulfill({ body: fs.readFileSync(f), contentType: types[path.extname(f)] }); }
  if (route.request().method() === 'POST' && url.pathname === '/api/org-unit-rules/test')
    return route.fulfill({ json: { winner: { id: 1, org_unit_code: P('wcode'), field: P('wf'), match_type: P('wm'), pattern: P('wp') }, matches: [] } });
  if (url.pathname in API) return route.fulfill({ json: API[url.pathname] });
  return route.fulfill({ json: [] });
});
const count = () => p.evaluate(() => [...document.querySelectorAll('[data-xss]')].map(e => e.dataset.xss));
const report = {};
for (const view of ['supervision', 'report', 'calls', 'quality', 'capacity', 'users', 'orgunits', 'audit', 'account']) {
  await p.goto(`http://app.test/?v=${view}#${view}`); await p.waitForTimeout(900);
  report[view] = await count(); report[view + "#text"] = await p.evaluate(() => (document.body.innerText.match(/data-xss=/g) || []).length + (document.body.innerHTML.match(/data-xss=&quot;/g) || []).length);
  if (view === 'calls') { await p.click('#callRows tr.selectable td:first-child'); await p.waitForTimeout(700); report['calls-drawer'] = await count(); report['drawer#text'] = await p.evaluate(() => (document.getElementById('callDrawerBody').textContent.match(/data-xss=/g) || []).length); report['drawer#head'] = await p.evaluate(() => document.getElementById('callDrawerBody').textContent.replace(/\s+/g,' ').slice(0,200)); report['trace#href'] = await p.evaluate(() => document.getElementById('callTrace').href);
    // hover the fps chart
    const band = await p.$('#callDrawerBody .hover-band'); if (band) { await band.hover(); report['calls-fps-hover'] = await count(); } }
  if (view === 'capacity') { const band = await p.$('.hover-band'); if (band) { await band.hover(); report['capacity-hover'] = await count(); } }
  if (view === 'orgunits') { await p.click('[data-action="edit-rule"]'); await p.waitForTimeout(300); report['orgunits-rule-dialog'] = await count();
    await p.keyboard.press('Escape'); await p.click('[data-action="delete-rule"]'); await p.waitForTimeout(300); report['orgunits-confirm'] = await count();
    await p.keyboard.press('Escape'); await p.fill('#ouTestUri', 'a').catch(() => {}); await p.click('#ouTestForm button[type=submit]').catch(() => {}); await p.waitForTimeout(400); report['orgunits-test'] = await count();
    report['orgunits-test-text'] = await p.$eval('#ouTestResult', e => e.textContent.slice(0, 120)).catch(() => 'n/a'); }
  if (view === 'users') { await p.click('[data-action="edit"]'); await p.waitForTimeout(300); report['users-dialog'] = await count(); await p.keyboard.press('Escape');
    await p.click('[data-action="delete"]').catch(() => {}); await p.waitForTimeout(300); report['users-confirm'] = await count(); }
}
const bad = Object.entries(report).filter(([k, v]) => Array.isArray(v) && v.length);
console.log(JSON.stringify(report, null, 0).slice(0, 1500));
console.log('INJECTED:', bad.length ? JSON.stringify(bad) : 'none', '| dialogs:', dialogs.length, '| errors:', errors.join(' | ') || 'none');
process.exitCode = bad.length || dialogs.length ? 1 : 0;
// Evidence the poison reached the screen as text:
await p.goto('http://app.test/?v=calls#calls'); await p.waitForTimeout(800);
console.log('text sample:', (await p.$eval('#callRows', e => e.textContent)).replace(/\s+/g, ' ').slice(0, 160));
await b.close();
