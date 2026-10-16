// Loaded before either page's own script, which is why these are plain
// globals: nothing here is worth a module for.
const BRAND = {
  name: 'SIPMediaGW',
  tagline: '',
  logo: '/favicon/favicon.svg',                       // e.g. '/pairing/static/logo.svg'; empty hides it

  // The pairing page's footer link. The companion page has no room for it.
  // Keep per-language URLs when the docs route is locale-sensitive.
  docUrl: '/docs',
  docUrlFr: '/docs?lang=fr',
  docUrlEn: '/docs?lang=en',
  docLabelFr: 'Documentation et présentation du service',
  docLabelEn: 'Service documentation and overview',
};

document.title = BRAND.name;
const iconLink = document.querySelector('link[rel="icon"]');
if (iconLink) {
  iconLink.href = BRAND.logo || '';
}
document.querySelector('#brand-name').textContent = BRAND.name;
document.querySelector('#brand-tagline').textContent = BRAND.tagline;
if (BRAND.logo) {
  const logo = document.getElementById('brand-logo');
  if (logo) {
    logo.src = BRAND.logo;
    logo.alt = BRAND.name;
  }
}