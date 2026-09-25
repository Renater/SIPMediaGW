-- Gateway Manager — reporting, lot 2 (partial): concurrency
--
-- Apply after schema_pool.sql. Additive.
--
-- Two different questions, two different sources:
--
--   "how many calls at once, at most, on that day"  -> a sweep over call
--      start/end events, which catches every call however short;
--   "how many calls at once, typically"             -> the sampled pool, where
--      each reading carries equal weight, so a percentile is meaningful.
--
-- A percentile computed over the sweep would be wrong: its events are not
-- evenly spaced in time, so a quiet hour and a busy minute would count the
-- same. pool_samples is taken at a fixed interval and is the right basis.
--
-- The peak alone sizes for the worst minute of the month; the p95 says what the
-- service actually carries. Both are published, and the gap between them is
-- what a discussion about the floor is about.

DROP VIEW IF EXISTS hourly_concurrency;

-- Concurrency by hour and day type — the shape the scaler is configured in.
--
-- A percentile taken over a whole month is dragged down by nights and weekends:
-- most samples are zero, so p95 lands well below the level the busy hours
-- actually need, and sizing on it under-provisions. Split by hour, each slot
-- carries its own distribution and reads straight across to the scaler, whose
-- configuration is per day type and per time slot.
--
-- The peak here is the highest sample of the slot. A burst shorter than the
-- sampling interval can escape it; daily_peak_concurrency, built from call
-- events, does not — the summary reads it for that reason.
-- The period is a parameter so that samples are filtered BEFORE they are
-- aggregated: filtered after, on the view, every page read the whole
-- history (3.9 s for a month once a year of samples is stored).
-- One function, two groupings. Over a period (the console), a slot is one
-- row whatever the number of months the period spans: grouped by month too,
-- a year gave twelve rows per hour, and the chart kept one of them at
-- random. By month (the whole-history view, the restore check), month
-- says which one; over a period it is NULL.
CREATE OR REPLACE FUNCTION hourly_concurrency_rows(p_since timestamptz, p_until timestamptz, p_by_month boolean)
RETURNS TABLE (
    month timestamptz,
    day_type text,
    hour integer,
    median numeric,
    p90 numeric,
    p95 numeric,
    p99 numeric,
    peak integer,
    avg_concurrent numeric,
    samples bigint,
    days bigint
) LANGUAGE sql STABLE AS $$
SELECT m AS month,
       COALESCE(weekday, day_group)                                     AS day_type,
       hour,
       ROUND(percentile_cont(0.50) WITHIN GROUP (ORDER BY ivr + in_call)::numeric, 1) AS median,
       ROUND(percentile_cont(0.90) WITHIN GROUP (ORDER BY ivr + in_call)::numeric, 1) AS p90,
       ROUND(percentile_cont(0.95) WITHIN GROUP (ORDER BY ivr + in_call)::numeric, 1) AS p95,
       ROUND(percentile_cont(0.99) WITHIN GROUP (ORDER BY ivr + in_call)::numeric, 1) AS p99,
       MAX(ivr + in_call)                                               AS peak,
       ROUND(AVG(ivr + in_call), 2)                                     AS avg_concurrent,
       COUNT(*)                                                         AS samples,
       COUNT(DISTINCT day)                                              AS days
FROM (SELECT *, CASE WHEN p_by_month THEN month END AS m
        FROM pool_sample_days_between(p_since, p_until)) s
GROUP BY GROUPING SETS ((m, weekday, hour), (m, day_group, hour))
-- The group set has no group for a weekend sample: that row is dropped, and
-- Saturday and Sunday exist once, as their own day.
HAVING COALESCE(weekday, day_group) IS NOT NULL
$$;

CREATE OR REPLACE FUNCTION hourly_concurrency_between(p_since timestamptz, p_until timestamptz)
RETURNS TABLE (
    month timestamptz,
    day_type text,
    hour integer,
    median numeric,
    p90 numeric,
    p95 numeric,
    p99 numeric,
    peak integer,
    avg_concurrent numeric,
    samples bigint,
    days bigint
) LANGUAGE sql STABLE AS $$
    SELECT * FROM hourly_concurrency_rows(p_since, p_until, false)
$$;

-- The whole history, for reading by hand and for the restore check. The
-- console calls hourly_concurrency_between() with its period.
CREATE VIEW hourly_concurrency AS SELECT * FROM hourly_concurrency_rows('-infinity', 'infinity', true);

COMMENT ON VIEW hourly_concurrency IS
    'Concurrent calls by month, day type (a weekday, or default = Monday to Friday) '
    'and hour. Percentiles are per slot on '
    'purpose: computed over a whole month they are dragged down by nights and '
    'weekends and would under-size the busy hours.';
