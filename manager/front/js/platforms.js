/* Conferencing platforms: display names and icons.

   Single source of truth for the three places that show a platform (the pool
   table, the call log and the report legend), so a new connector is added
   once. The icon set is the one the IVR ships, served from /static/icons. */

import { esc, norm } from './format.js';

const ICON_URL = '/static/icons/';

/* Connector key, as the gateway reports it in "browsing". */
export const PLATFORMS = {
  jitsi: 'Jitsi', visio: 'Visio', webinaire: 'Webinaire', bigbluebutton: 'BigBlueButton',
  bbbesr: 'BBB ESR', livekit: 'LiveKit', teams: 'Teams', googlemeet: 'Google Meet',
  nextcloud: 'Nextcloud Talk',
};

/* A connector the table does not know is not a platform to display: on a
   monthly report it reads as a product nobody recognises. Unknown keys are
   grouped under one entry instead. */
/* A fixed colour per connector.

   Assigning colours by rank makes them move: a month where Jitsi is second and
   the next where it is third would show it in two different colours, and a
   reader comparing two slides would read a change that did not happen. Bound to
   the connector, the colour is stable across periods and across charts. */
export const PLATFORM_COLORS = {
  visio: '#000091',          // DSFR blue-france
  jitsi: '#68a532',          // DSFR green-bourgeon
  webinaire: '#c8aa39',      // DSFR yellow-tournesol
  bigbluebutton: '#a558a0',  // DSFR purple-glycine
  bbbesr: '#e4794a',         // DSFR orange-terre-battue
  livekit: '#465f9d',        // DSFR blue-ecume
  teams: '#00a95f',          // DSFR green-emeraude
  googlemeet: '#c08c65',     // DSFR brown-caramel
  nextcloud: '#e18b76',      // DSFR pink-macaron
};

export const platformColor = key => {
  const value = norm(key);
  return (value && PLATFORM_COLORS[value]) || null;
};

export const isKnownPlatform = key => {
  const value = norm(key);
  return value != null && Object.prototype.hasOwnProperty.call(PLATFORMS, value);
};

export const platformLabel = key => {
  const value = norm(key);
  return value == null ? null : (PLATFORMS[value] || value);
};

/* Icon markup, or an empty string for an unknown or unsafe key. The image is
   dropped on error rather than left broken: see attachIconFallback. */
export function platformIcon(key) {
  const value = norm(key);
  if (!value || !/^[a-z0-9]+$/.test(value)) return '';
  return `<img src="${ICON_URL}${value}.png" alt="" data-fallback="1">`;
}

export function platformCell(key, dash = '<span class="dim">—</span>') {
  const label = platformLabel(key);
  if (label == null) return dash;
  return `<span class="platform">${platformIcon(key)}<span>${esc(label)}</span></span>`;
}

/* A missing icon (unknown connector, icons not deployed) is removed rather
   than shown as a broken image. */
export function attachIconFallback(container) {
  for (const image of container.querySelectorAll('img[data-fallback]')) {
    image.addEventListener('error', () => image.remove(), { once: true });
  }
}
