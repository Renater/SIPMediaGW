-- Gateway Manager — every close reason, and whether it is expected
--
-- Apply after schema_reporting_lot0.sql.
--
-- The previous view only opened `ivr_only`, which answered "what have we not
-- classified yet" — a maintainer's question. A reader wants the other one: what
-- ends a call here, and is that normal. So every reason is listed, each carrying
-- how the call was classified and whether the reason is one of the failures the
-- whitelist recognises.

DROP VIEW IF EXISTS close_reasons;

CREATE VIEW close_reasons AS
SELECT COALESCE(NULLIF(close_reason, ''), '(aucune cause)')   AS close_reason,
       outcome,
       is_technical_failure(close_reason)                     AS is_failure,
       COUNT(*)                                               AS sessions,
       ROUND(AVG(occupancy_s))                                AS avg_occupancy_s,
       MIN(call_start)                                        AS first_seen,
       MAX(call_start)                                        AS last_seen
FROM calls
WHERE is_user_call(main_app)
GROUP BY 1, 2, 3;

COMMENT ON VIEW close_reasons IS
    'Every close reason with the outcome it produced and whether the whitelist '
    'counts it as a technical failure. A reason that ends completed calls is '
    'normal however alarming it reads: the conference had been joined.';
