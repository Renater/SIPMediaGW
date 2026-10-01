-- One-off: calls whose platform is not a connector key.
--
-- Before the ingestion checked it, a gateway error printed with the word
-- "browsing:" in it ("Error while browsing: Message: javascript error...")
-- was stored as the platform of the call. The text is still in `raw`; the
-- platform becomes absent, as the ingestion now stores it. Replaying this
-- file changes nothing. Run once per deployment that predates the check.

BEGIN;
UPDATE calls SET platform = NULL
 WHERE platform IS NOT NULL
   AND platform !~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$';
COMMIT;
