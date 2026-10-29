// Loaded before either page's own script, which is why these are plain
// globals: nothing here is worth a module for.
const BRAND = {
  name: 'SIPMediaGW',
  tagline: '',
  logo: '/favicon/favicon.svg',                       // e.g. '/pairing/static/logo.svg'; empty hides it

  // The pairing page's footer link: the service's presentation, the portal.
  // The pure documentation stays one step away, in the portal's own footer.
  // Keep per-language URLs if the target route ever becomes locale-sensitive.
  docUrl: '/portal',
  docLabelFr: 'Présentation du service',
  docLabelEn: 'Service overview',
};

document.title = BRAND.name;
const iconLink = document.querySelector('link[rel="icon"]');
if (iconLink) {
  iconLink.href = BRAND.logo || '';
}
// The portal loads this file too, for BRAND.name alone: guard the elements
// it does not have.
const brandName = document.querySelector('#brand-name');
if (brandName) brandName.textContent = BRAND.name;
const brandTagline = document.querySelector('#brand-tagline');
if (brandTagline) brandTagline.textContent = BRAND.tagline;
if (BRAND.logo) {
  const logo = document.getElementById('brand-logo');
  if (logo) {
    logo.src = BRAND.logo;
    logo.alt = BRAND.name;
  }
}
