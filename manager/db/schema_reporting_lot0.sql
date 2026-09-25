-- Manager — reporting: groundwork (recompute functions, the scope of user calls, monthly view)
--
-- Apply after schema.sql and schema_org_units.sql, as gw_manager on gw_manager.
-- Everything here is additive: existing views keep their names, and the two
-- that change their result do so to fix a known double count (see §3).

-- 1. Audit of recomputations -------------------------------------------------
--
-- Both recompute functions rewrite history: an outcome or an org unit changes
-- for calls that were already reported. The monthly deliverable is a slide deck,
-- so the published figures are frozen the day they are sent — but someone will
-- eventually compare a slide with the tool and find a gap. This table is what
-- lets that gap be explained instead of suspected.

CREATE TABLE IF NOT EXISTS recompute_log (
    id          BIGSERIAL PRIMARY KEY,
    ran_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    target      TEXT        NOT NULL CHECK (target IN ('outcomes', 'org_units')),
    rows_seen   BIGINT      NOT NULL,   -- rows examined
    rows_moved  BIGINT      NOT NULL,   -- rows whose value actually changed
    ran_by      TEXT        NOT NULL DEFAULT current_user,
    note        TEXT
);

COMMENT ON COLUMN recompute_log.rows_moved IS
    'Rows whose value changed, not rows touched: a recompute that moves nothing '
    'is worth recording too, since it proves the rules were already applied.';

-- 2. Recomputing outcomes ----------------------------------------------------
--
-- is_technical_failure() is a whitelist of six patterns, and everything outside
-- it falls into ivr_only. That list will grow as production shows which reasons
-- really are failures — and every time it grows, the history keeps the old
-- classification unless it is replayed. Without this function, monthly series
-- stop being comparable at the exact moment one starts looking at them.
--
-- The rules are the trigger's rules, deliberately duplicated rather than
-- factored out: a BEFORE INSERT trigger works on NEW, a bulk UPDATE on a set.
-- Keeping them side by side in the same file is what makes a divergence
-- visible; tests/test_outcome_rules.py checks they agree.

CREATE OR REPLACE FUNCTION recompute_outcomes(p_note TEXT DEFAULT NULL)
RETURNS TABLE (rows_seen BIGINT, rows_moved BIGINT) LANGUAGE plpgsql AS $$
DECLARE seen BIGINT; moved BIGINT;
BEGIN
    SELECT count(*) INTO seen FROM calls;

    WITH recomputed AS (
        SELECT id,
               CASE WHEN NOT established             THEN 'not_established'
                    WHEN room IS NOT NULL            THEN 'completed'
                    WHEN is_technical_failure(close_reason) THEN 'failed'
                    ELSE 'ivr_only' END AS new_outcome
        FROM calls
    ),
    changed AS (
        UPDATE calls c
           SET outcome = r.new_outcome,
               -- duration_s follows the outcome, as it does on insert: gateway
               -- time is consumed whatever happens, call duration only counts
               -- when a conference was joined. A call moving to completed had
               -- its duration zeroed on insert: occupancy is the best left.
               duration_s = CASE WHEN r.new_outcome = 'completed'
                                 THEN COALESCE(NULLIF(c.duration_s, 0), c.occupancy_s, 0)
                                 ELSE 0 END
          FROM recomputed r
         WHERE c.id = r.id AND c.outcome IS DISTINCT FROM r.new_outcome
        RETURNING 1
    )
    SELECT count(*) INTO moved FROM changed;

    INSERT INTO recompute_log (target, rows_seen, rows_moved, note)
    VALUES ('outcomes', seen, moved, p_note);

    RETURN QUERY SELECT seen, moved;
END $$;

COMMENT ON FUNCTION recompute_outcomes(TEXT) IS
    'Replays the outcome rules over the whole history. Run it after every change '
    'to is_technical_failure(), and pass a note saying which pattern was added.';

-- 3. Recomputing org units, with the same audit ------------------------------
--
-- The previous version returned ROW_COUNT of an unconditional UPDATE, which
-- counts rows touched, not rows moved — it reported the whole table every time.
-- Same signature, an honest count, and an entry in the log.

-- The first version had another signature; CREATE OR REPLACE would keep it
-- as an overload and make recompute_org_units() ambiguous.
DROP FUNCTION IF EXISTS recompute_org_units();
CREATE OR REPLACE FUNCTION recompute_org_units(p_note TEXT DEFAULT NULL)
RETURNS TABLE (rows_seen BIGINT, rows_moved BIGINT) LANGUAGE plpgsql AS $$
DECLARE seen BIGINT; moved BIGINT;
BEGIN
    SELECT count(*) INTO seen FROM calls;

    WITH resolved AS (
        SELECT id, resolve_org_unit(org_unit_uri(source_uri, source_number, source_domain),
                                    source_name) AS new_unit
        FROM calls
    ),
    changed AS (
        UPDATE calls c SET org_unit = r.new_unit
          FROM resolved r
         WHERE c.id = r.id AND c.org_unit IS DISTINCT FROM r.new_unit
        RETURNING 1
    )
    SELECT count(*) INTO moved FROM changed;

    INSERT INTO recompute_log (target, rows_seen, rows_moved, note)
    VALUES ('org_units', seen, moved, p_note);

    RETURN QUERY SELECT seen, moved;
END $$;

-- 4. What is a user call ------------------------------------------------------
--
-- main_app is 'baresip', 'recording' or 'streaming'. A recording gateway joins
-- the conference like any participant: it gets a room, so outcome = 'completed',
-- and until now it was counted as a user call with its own duration and
-- platform. A recorded meeting counted twice.
--
-- Usage and quality count user calls only. Capacity counts everything, since a
-- service session consumes a gateway exactly like a call.
--
-- NULL is treated as a user call: main_app has only been pushed since the
-- payload carried it, and older rows should not silently vanish from the
-- volumes.

CREATE OR REPLACE FUNCTION is_user_call(p_main_app TEXT) RETURNS BOOLEAN
LANGUAGE sql IMMUTABLE AS $$
    SELECT p_main_app IS NULL OR p_main_app NOT IN ('recording', 'streaming')
$$;

-- 5. Views ---------------------------------------------------------------------

-- Service rendered: user calls only. Recording and streaming sessions are
-- excluded here; they still count in the pool views, since they hold a VM.
CREATE OR REPLACE VIEW monthly_service AS
SELECT date_trunc('month', call_start)     AS month,
       COUNT(*)                            AS calls,
       ROUND(SUM(duration_s) / 3600.0, 1)  AS hours,
       ROUND(AVG(duration_s))              AS avg_seconds
FROM calls
WHERE outcome = 'completed' AND call_start IS NOT NULL AND is_user_call(main_app)
GROUP BY 1;

