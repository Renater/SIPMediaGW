BEGIN;

-- Peak concurrent calls per day: sweep over start/end events.
-- Every established SIP session counts, IVR-only included: a caller sitting on
-- the IVR holds a gateway exactly like a caller in a conference.
CREATE OR REPLACE VIEW daily_peak_concurrency AS
WITH ev AS (
    SELECT call_start AS t,  1 AS d FROM calls WHERE call_start IS NOT NULL AND call_end IS NOT NULL
    UNION ALL
    SELECT call_end   AS t, -1 AS d FROM calls WHERE call_start IS NOT NULL AND call_end IS NOT NULL
),
run AS (SELECT t, SUM(d) OVER (ORDER BY t, d ROWS UNBOUNDED PRECEDING) AS concurrent FROM ev)
-- t::date follows the session time zone, set by the application.
SELECT t::date AS day, MAX(concurrent) AS peak_concurrent FROM run GROUP BY 1;

COMMIT;
