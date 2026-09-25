-- Example reference data — NOT part of the schema.
-- Copy, adapt to your own numbering plan and naming conventions, keep it out of
-- the repository, and run SELECT recompute_org_units(); after any change.
-- The console (Settings > Units) does the same, with an audit line per change.

INSERT INTO org_units (code, label) VALUES
    ('SALES',   'Sales department'),
    ('SUPPORT', 'Customer support')
ON CONFLICT (code) DO NOTHING;

-- Read top to bottom, the last rule that matches wins (position). Literal,
-- case-insensitive prefix or suffix on the CALLER only: its SIP URI
-- (user@domain, without "sip:") or its display name (alias). A number is a
-- prefix of the URI, a domain a suffix of it.
INSERT INTO org_unit_rules (org_unit_code, field, match_type, pattern, comment, position) VALUES
    ('SALES',   'uri',   'prefix', '21',                   'extensions 21xxxxxx',  1),
    ('SALES',   'alias', 'prefix', 'ACME_SALES_',          'room display names',   2),
    ('SUPPORT', 'uri',   'suffix', '@support.example.org', 'dedicated SIP domain', 3)
ON CONFLICT (field, match_type, pattern) DO NOTHING;

SELECT recompute_org_units();
