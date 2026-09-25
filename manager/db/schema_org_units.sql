-- Manager — organisational units (generic reporting dimension)
-- Apply after schema.sql, as gw_manager on database gw_manager.
--
-- An org unit is any tenant-side grouping an operator reports on: a department,
-- a campus component, a customer. Calls are attached to one by rules matching the
-- calling endpoint. No unit or rule is shipped: the reference data belongs to the
-- deployment, not to this schema (see org_units.sample.sql for an example).

CREATE TABLE IF NOT EXISTS org_units (
    code            TEXT PRIMARY KEY,
    label           TEXT NOT NULL,
    parent_code     TEXT REFERENCES org_units(code) ON DELETE SET NULL,
    active          BOOLEAN NOT NULL DEFAULT true
);

-- Matching rules, on the CALLING endpoint only (since P23), two fields:
--   uri    -> the caller's SIP URI, user@domain, without its scheme
--   alias  -> the caller's display name (source_name)
-- peer_display_name is the called side: it never classifies the caller.
-- A number is a prefix of the URI ("21"), a domain a suffix of it
-- ("@visio.example.org", or ".example.org" for every subdomain).
--
-- match_type: 'prefix' or 'suffix', literal (no wildcard: "1test" does not
-- start with "test") and case-insensitive (ABC = aBc). 'regex' is still
-- read but the console does not write it.
--
-- Order (since P22): the rules are read top to bottom, like an Expressway
-- transform list, and the LAST one that matches decides. A rule assigns an
-- entity and changes nothing else, so this is the matching rule with the
-- highest position. priority is no longer read.
CREATE TABLE IF NOT EXISTS org_unit_rules (
    id              BIGSERIAL PRIMARY KEY,
    org_unit_code   TEXT NOT NULL REFERENCES org_units(code) ON DELETE CASCADE,
    field           TEXT NOT NULL CHECK (field IN ('uri', 'alias')),
    match_type      TEXT NOT NULL DEFAULT 'prefix' CHECK (match_type IN ('prefix', 'suffix', 'regex')),
    pattern         TEXT NOT NULL,
    priority        INTEGER NOT NULL DEFAULT 100,
    active          BOOLEAN NOT NULL DEFAULT true,
    comment         TEXT,
    UNIQUE (field, match_type, pattern)
);

-- A regex that does not compile would abort ingestion, so it is rejected at
-- write time instead: an operator editing rules gets an error on the rule, and
-- the call pipeline is never at risk.
-- Replayed on a deployed database, CREATE TABLE does not change the check.
ALTER TABLE org_unit_rules DROP CONSTRAINT IF EXISTS org_unit_rules_match_type_check;
ALTER TABLE org_unit_rules ADD CONSTRAINT org_unit_rules_match_type_check
    CHECK (match_type IN ('prefix', 'suffix', 'regex'));
ALTER TABLE org_unit_rules ADD COLUMN IF NOT EXISTS position INTEGER;
ALTER TABLE org_unit_rules ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ;
ALTER TABLE org_unit_rules ADD COLUMN IF NOT EXISTS updated_by TEXT;

-- P23: three fields became two. A number was a prefix of the URI's user
-- part, so a prefix of the URI; a name is the alias; a domain rule becomes a
-- suffix of the URI behind its "@" (a domain prefix meant that domain).
ALTER TABLE org_unit_rules DROP CONSTRAINT IF EXISTS org_unit_rules_field_check;
UPDATE org_unit_rules SET field = 'uri' WHERE field = 'number';
UPDATE org_unit_rules SET field = 'alias' WHERE field = 'name';
UPDATE org_unit_rules SET field = 'uri', match_type = 'suffix', pattern = '@' || pattern
 WHERE field = 'domain' AND match_type = 'prefix';
UPDATE org_unit_rules SET field = 'uri' WHERE field = 'domain';
ALTER TABLE org_unit_rules ADD CONSTRAINT org_unit_rules_field_check CHECK (field IN ('uri', 'alias'));

-- Rules from before P22 have no position. Their effective order was "first
-- match wins": lowest priority, prefix before regex, longest pattern. The
-- reverse of that order, read "last match wins", decides the same way.
UPDATE org_unit_rules r SET position = o.position
  FROM (SELECT id, row_number() OVER (
                   ORDER BY priority DESC,
                            CASE match_type WHEN 'prefix' THEN 0 ELSE 1 END DESC,
                            length(pattern), id DESC) AS position
          FROM org_unit_rules) o
 WHERE r.id = o.id AND r.position IS NULL
   AND NOT EXISTS (SELECT 1 FROM org_unit_rules WHERE position IS NOT NULL);

-- Who changed which rule or entity, when, and from what to what. One row per
-- change, written in the same statement as the change.
CREATE TABLE IF NOT EXISTS org_unit_audit (
    id      BIGSERIAL PRIMARY KEY,
    at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor   TEXT NOT NULL,
    action  TEXT NOT NULL,          -- unit_create, unit_update, rule_create, rule_update, rule_delete, rules_order, recompute
    target  TEXT NOT NULL,          -- entity code, or "rule <id>"
    detail  JSONB NOT NULL DEFAULT '{}'::jsonb   -- before / after
);
CREATE INDEX IF NOT EXISTS org_unit_audit_at_idx ON org_unit_audit (at DESC);

CREATE OR REPLACE FUNCTION org_unit_rules_validate() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.match_type = 'regex' THEN
        BEGIN
            PERFORM 'probe' ~* NEW.pattern;
        EXCEPTION WHEN OTHERS THEN
            RAISE EXCEPTION 'invalid regular expression: %', NEW.pattern;
        END;
    END IF;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS org_unit_rules_validate_trg ON org_unit_rules;
CREATE TRIGGER org_unit_rules_validate_trg BEFORE INSERT OR UPDATE ON org_unit_rules
    FOR EACH ROW EXECUTE FUNCTION org_unit_rules_validate();

ALTER TABLE calls ADD COLUMN IF NOT EXISTS org_unit TEXT REFERENCES org_units(code);
CREATE INDEX IF NOT EXISTS calls_org_unit_idx ON calls (org_unit);

-- Signatures changed with P23 (three caller fields became two).
DROP FUNCTION IF EXISTS resolve_org_unit(TEXT, TEXT, TEXT);
DROP FUNCTION IF EXISTS org_unit_value(TEXT, TEXT, TEXT, TEXT);

-- The caller's URI as rules see it: user@domain, no "sip:" or "sips:". Built
-- from its parts when the gateway sent them without the URI.
CREATE OR REPLACE FUNCTION org_unit_uri(p_uri TEXT, p_number TEXT, p_domain TEXT)
RETURNS TEXT LANGUAGE sql IMMUTABLE AS $$
    SELECT COALESCE(NULLIF(regexp_replace(p_uri, '^sips?:', '', 'i'), ''),
                    CASE WHEN p_number IS NOT NULL AND p_domain IS NOT NULL
                         THEN p_number || '@' || p_domain END)
$$;

CREATE OR REPLACE FUNCTION org_unit_value(p_field TEXT, p_uri TEXT, p_alias TEXT)
RETURNS TEXT LANGUAGE sql IMMUTABLE AS $$
    SELECT CASE p_field WHEN 'uri' THEN p_uri WHEN 'alias' THEN p_alias END
$$;

-- starts_with() and right(): literal, no wildcard ('_' is one for LIKE, and
-- display names contain it). lower() on both sides: ABC = aBc.
CREATE OR REPLACE FUNCTION org_unit_rule_matches(p_type TEXT, p_pattern TEXT, p_value TEXT)
RETURNS BOOLEAN LANGUAGE sql IMMUTABLE AS $$
    SELECT p_value IS NOT NULL AND CASE p_type
        WHEN 'prefix' THEN starts_with(lower(p_value), lower(p_pattern))
        WHEN 'suffix' THEN right(lower(p_value), length(p_pattern)) = lower(p_pattern)
        ELSE p_value ~* p_pattern END
$$;

-- The last rule that matches, in position order, among active rules of active
-- entities.
CREATE OR REPLACE FUNCTION resolve_org_unit(p_uri TEXT, p_alias TEXT)
RETURNS TEXT LANGUAGE sql STABLE AS $$
    SELECT r.org_unit_code
      FROM org_unit_rules r
      JOIN org_units u ON u.code = r.org_unit_code AND u.active
     WHERE r.active
       AND org_unit_rule_matches(r.match_type, r.pattern, org_unit_value(r.field, p_uri, p_alias))
     ORDER BY r.position DESC NULLS LAST, r.id DESC
     LIMIT 1
$$;

-- Resolution must never break ingestion: a runtime error (a regex that compiles
-- but misbehaves on some input) leaves org_unit NULL rather than losing the call.
CREATE OR REPLACE FUNCTION calls_set_org_unit() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    BEGIN
        NEW.org_unit := resolve_org_unit(org_unit_uri(NEW.source_uri, NEW.source_number, NEW.source_domain),
                                         NEW.source_name);
    EXCEPTION WHEN OTHERS THEN
        NEW.org_unit := NULL;
        RAISE WARNING 'org unit resolution failed for call %: %', NEW.call_id, SQLERRM;
    END;
    RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS calls_org_unit_trg ON calls;
CREATE TRIGGER calls_org_unit_trg BEFORE INSERT ON calls
    FOR EACH ROW EXECUTE FUNCTION calls_set_org_unit();

-- recompute_org_units() lives in schema_reporting_lot0.sql, which logs each
-- run. An earlier definition here, with another signature, made the
-- zero-argument call ambiguous.

-- Reporting views ------------------------------------------------------------
