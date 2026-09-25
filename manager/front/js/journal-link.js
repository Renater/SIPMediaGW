/* From a count to the calls behind it.

   The Quality view hands the Journal a period and an exact filter (a close
   reason with its outcome, or a video state), then opens it. Kept in module
   state, not in the address or in storage: it is a one-shot hand-over, taken
   by the Journal when it mounts. */

let pending = null;

export function openJournal(link) {
  pending = link;
  const entry = document.querySelector('.nav[data-view="calls"]');
  if (entry) entry.click();
}

export function takeJournalFilter() {
  const link = pending;
  pending = null;
  return link;
}
