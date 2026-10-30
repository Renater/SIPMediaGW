/* The portal's script. The page inside the phone owns the theme and language
   switches (the pairing page's toolbar); this page follows them through the
   localStorage keys they share, translates its own words, and fits the phone
   frame to the page's own height so nothing scrolls inside the frame. */
(function () {
  'use strict';

  const live = document.getElementById('live');
  const hub = document.getElementById('hub');

  // The QR code points at the portal's own URL with ?pairingCode=..., but the
  // code has to reach the pairing page inside the phone, which reads it from
  // its own address — forward it to the live document.
  const pairingCode = new URLSearchParams(location.search).get('pairingCode');
  if (pairingCode) live.src = '/pairing?pairingCode=' + encodeURIComponent(pairingCode);

  /* ---------- FR/EN, like the pairing page: same 'lang' key ---------- */
  const TEXTS = {
    fr: {
      // The document title's brand part is set from BRAND in applyLang.
      title: 'Le service',
      eyebrow: 'Connecteur de salles universel',
      lead: "Vos salles de réunion rejoignent toutes les plateformes de visioconférence, en toute simplicité et en toute sécurité.",
      capRoom: "N'importe quelle salle",
      capMeeting: "N'importe quelle réunion",
      sip: 'et tout terminal SIP',
      phone: 'Cette interface est réelle, interagissez avec elle.',
      phoneTitle: "Pages d'appairage et de pilotage",
      howTitle: 'Comment ça marche',
      step1t: 'Le code',          step1: "Un code à 5 caractères s'affiche sur l'écran de la salle.",
      step2t: "L'appairage",      step2: "Saisissez-le dans l'interface ci-contre.",
      step2below: "Saisissez-le dans l'interface ci-dessous.",
      step3t: 'La réunion',       step3: 'Choisissez la plateforme et la réunion, la salle la rejoint.',
      footService: 'Un service RENATER',
      footDoc: 'Documentation',
      footLegal: 'Mentions légales',
      // {brand} is the solution's name, filled in by applyLang from BRAND.
      hubLabel: "N'importe quelle salle : Cisco, Poly, Yealink, Lifesize, Crestron, Huawei, AVer et tout terminal SIP. Via {brand}, n'importe quelle réunion : Rendez-vous, Webinaire de l'État, Visio, Classe virtuelle de l'ESR."
    },
    en: {
      title: 'The service',
      eyebrow: 'Universal room connector',
      lead: 'Your meeting rooms join every videoconference platform, simply and securely.',
      capRoom: 'Any room',
      capMeeting: 'Any meeting',
      sip: 'and any SIP endpoint',
      phone: 'The interface is real, feel free to interact with it.',
      phoneTitle: 'Pairing and control pages',
      howTitle: 'How it works',
      step1t: 'The code',         step1: 'A 5-character code is displayed on the room screen.',
      step2t: 'Pairing',          step2: 'Enter it in the interface alongside.',
      step2below: 'Enter it in the interface below.',
      step3t: 'The meeting',      step3: 'Pick the platform and the meeting, the room joins it.',
      footService: 'A RENATER service',
      footDoc: 'Documentation',
      footLegal: 'Legal notice',
      hubLabel: "Any room: Cisco, Poly, Yealink, Lifesize, Crestron, Huawei, AVer and any SIP endpoint. Via {brand}, any meeting: Rendez-vous, Webinaire de l'État, Visio, Classe virtuelle de l'ESR."
    }
  };

  let lang = 'fr';
  try { lang = localStorage.getItem('lang') || 'fr'; } catch (e) {}
  if (!TEXTS[lang]) lang = 'fr';

  // Declared before applyLang: the step-2 copy, the headline and the diagram
  // all depend on the wide/narrow split and the solution's name. brand.js
  // (loaded in <head>) sets BRAND; the IIFE sees it through the shared global
  // scope.
  const WIDE = window.matchMedia('(min-width:62rem)');
  const brandName = (typeof BRAND !== 'undefined' && BRAND.name) || 'SIPMediaGW';

  // The diagram's gateway block is the pairing page's brand header: fill it
  // from BRAND here rather than in brand.js, which already ran in <head> —
  // before this page's markup existed.
  const gwName = document.querySelector('.hub__gw .brand__name');
  if (gwName) gwName.textContent = brandName;
  const gwLogo = document.querySelector('.hub__gw .brand__logo');
  if (gwLogo && typeof BRAND !== 'undefined' && BRAND.logo) {
    gwLogo.src = BRAND.logo;
    gwLogo.alt = brandName;
  }

  const applyLang = (l) => {
    const t = TEXTS[l];
    document.documentElement.lang = l;
    document.title = brandName // + ' — ' + t.title;
    document.querySelectorAll('[data-i18n]').forEach(el => { el.textContent = t[el.dataset.i18n]; });
    // The headline is the solution's name on its own line, its role below
    // (the role comes from data-i18n above): "SIPMediaGW / Connecteur de
    // salles universel".
    document.getElementById('hero-brand').textContent = brandName;
    // Step 2 points at the live interface: alongside it on wide screens, below
    // it when the phone presentation stacks the interface beneath the steps.
    document.querySelector('[data-i18n="step2"]').textContent =
      (!WIDE.matches && document.documentElement.classList.contains('presenting')) ? t.step2below : t.step2;
    hub.setAttribute('aria-label', t.hubLabel.replace('{brand}', brandName));
    live.setAttribute('title', t.phoneTitle);
    // The docs follow the page language, as the pairing page's link does.
    document.getElementById('foot-doc').href = '/docs?lang=' + l;
  };
  applyLang(lang);
  // The phone's own switch writes the shared key: follow it.
  window.addEventListener('storage', (e) => {
    if (e.key === 'lang' && TEXTS[e.newValue]) applyLang(e.newValue);
  });

  /* ---------- Theme: the phone's toggle writes the shared 'theme' key. ---------- */
  window.addEventListener('storage', (e) => {
    if (e.key === 'theme' && (e.newValue === 'dark' || e.newValue === 'light')) {
      document.documentElement.dataset.theme = e.newValue;
    }
  });

  /* ---------- Phone frame: the page renders at its natural 390px width and
     is scaled (var(--fit)) to fill the frame, so it never scrolls inside and
     the phone fills the available height. ---------- */
  const LOGICAL_W = 390;
  const screen = live.parentElement;
  let ro = null;

  const fitPhone = () => {
    const doc = live.contentDocument;
    if (!doc || !doc.body) return;
    if (WIDE.matches && document.documentElement.classList.contains('calling')) {
      // Call mode: the page is the screen — CSS sizes the iframe (100vh,
      // no scale), so the frame's inline sizing goes.
      live.style.height = '';
      screen.style.height = '';
      screen.style.setProperty('--fit', '1');
      return;
    }
    const pageH = Math.max(doc.documentElement.scrollHeight, doc.body.scrollHeight);
    live.style.height = pageH + 'px';
    if (!WIDE.matches) return;
    const app = document.querySelector('.app');
    const phone = document.querySelector('.phone');
    const cap = document.querySelector('.phone-cap');
    const cs = getComputedStyle(phone);
    const capH = cap ? cap.getBoundingClientRect().height + parseFloat(getComputedStyle(cap).marginTop) : 0;
    const notch = parseFloat(getComputedStyle(screen).paddingTop);
    const pagePad = parseFloat(getComputedStyle(document.querySelector('.page')).paddingBottom);
    // The footer is a sibling of .page, below it, and on wide the phone is the
    // tallest column: leave the footer's height in the budget so the whole
    // page fits the viewport without scrolling.
    const foot = document.querySelector('.foot');
    const footH = foot ? foot.getBoundingClientRect().height : 0;
    const availH = innerHeight - app.getBoundingClientRect().top - (parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom)) - capH - notch - pagePad - footH;
    const s = Math.max(.3, Math.min(screen.clientWidth / LOGICAL_W, availH / pageH));
    screen.style.setProperty('--fit', s);
    screen.style.height = (notch + pageH * s) + 'px';
  };

  /* ---------- Diagram: fixed 764px design width, scaled to the column.
     On phones the presentation mode lays it out vertically at full column
     width instead: nothing to scale, and any inline fit from a previous wide
     state must go. ---------- */
  const fitHub = () => {
    const inner = hub.querySelector('.hub__in');
    if (!WIDE.matches) { inner.style.transform = ''; hub.style.height = ''; return; }
    if (!hub.offsetWidth) return;
    const s = Math.min(1, hub.clientWidth / 764);
    inner.style.transform = s < 1 ? 'scale(' + s + ')' : '';
    hub.style.height = inner.offsetHeight * s + 'px';
  };

  /* ---------- Presentation mode: the pairing page's "Présentation du
     service" link toggles the hash in the parent page. The class is read in
     <head> before first paint on load; hashchange covers the in-page toggle,
     and the back button (which drops the hash) restores the interface. Once
     the live page has walked onto /interact (a successful pairing), the
     presentation closes itself — see the load handler. ---------- */
  const fitAll = () => { fitPhone(); fitHub(); };

  /* ---------- The call watcher: a successful pairing navigates the live
     page onto /interact, and the portal follows it. On phones the
     presentation has done its job: it closes itself and the interface takes
     the whole screen. On wide screens the showcase and the footer step aside
     (html.calling) and the phone takes the full height; when the call ends
     and the live page bounces back to /pairing, the showcase comes back.
     A light interval reads the live page's path (same origin). The load
     handler calls the same sync for the normal, immediate case, but the
     interval covers the live document being replaced before its load settles
     (a bounced page, a hanging subresource), where no load event would
     arrive. */
  let callWatcher = null;
  const stopCallWatcher = () => {
    if (callWatcher) { clearInterval(callWatcher); callWatcher = null; }
  };
  // The QR's ?pairingCode has done its job once the pairing succeeds (the live
  // page walks onto /interact): it leaves the address so a reload does not
  // re-prefill a code that has already been spent.
  const urlWithoutCode = (dropHash) => {
    const url = new URL(location.href);
    url.searchParams.delete('pairingCode');
    if (dropHash) url.hash = '';
    return url.pathname + url.search + url.hash;
  };
  const syncCallMode = () => {
    const html = document.documentElement;
    const presenting = html.classList.contains('presenting');
    if (!WIDE.matches && !presenting) { stopCallWatcher(); return; }
    let path = '';
    try { path = live.contentWindow.location.pathname; } catch (e) { return; }
    const inCall = path === '/interact';
    if (WIDE.matches) {
      if (inCall !== html.classList.contains('calling')) {
        html.classList.toggle('calling', inCall);
        if (inCall && new URLSearchParams(location.search).has('pairingCode')) {
          // replaceState: no history entry, so back does not hand the code back.
          history.replaceState(null, '', urlWithoutCode(false));
        }
        fitAll();   // the phone's budget changes with the showcase and footer
      }
    } else if (presenting && inCall) {
      // replaceState, not a hash change: no history entry, so the back button
      // does not re-enter the presentation. The QR's code leaves with the hash —
      // it has done its job and a reload must not re-prefill it.
      history.replaceState(null, '', urlWithoutCode(true));
      setPresenting();
      window.scrollTo(0, 0);
    }
  };
  const startCallWatcher = () => {
    if (callWatcher) return;
    if (!WIDE.matches && !document.documentElement.classList.contains('presenting')) return;
    callWatcher = setInterval(syncCallMode, 400);
  };

  /* ---------- Presentation mode: the pairing page's "Présentation du
     service" link toggles the hash in the parent page. The class is read in
     <head> before first paint on load; hashchange covers the in-page toggle,
     and the back button (which drops the hash) restores the interface. Once
     the live page has walked onto /interact, the presentation closes itself —
     see the call watcher above. ---------- */
  const setPresenting = () => {
    const on = location.hash === '#presentation';
    document.documentElement.classList.toggle('presenting', on);
    applyLang(lang);   // step 2's pointer (ci-contre / ci-dessous) follows the mode
    if (!WIDE.matches && on) window.scrollTo(0, 0);   // the presentation starts at the title
    if (on || WIDE.matches) startCallWatcher(); else stopCallWatcher();
    fitAll();
  };
  window.addEventListener('hashchange', setPresenting);
  // A direct #presentation load (a shared link): the class was already added
  // in the head. The watcher must run there as on wide screens, where the
  // presentation is always on.
  if (WIDE.matches || document.documentElement.classList.contains('presenting')) startCallWatcher();

  live.addEventListener('load', () => {
    fitAll();
    if (ro) ro.disconnect();
    ro = null;
    const doc = live.contentDocument;
    if (doc && typeof ResizeObserver !== 'undefined') {
      ro = new ResizeObserver(fitPhone);
      ro.observe(doc.querySelector('.wrap') || doc.body);
    }
    syncCallMode();
  });
  if (typeof ResizeObserver !== 'undefined') new ResizeObserver(fitHub).observe(hub);
  // The wide/narrow split decides whether the watcher is needed.
  window.addEventListener('resize', () => { fitAll(); startCallWatcher(); });
})();
