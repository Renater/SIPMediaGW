-- Gateway Manager — reporting, lot 1: capacity
--
-- Apply after schema_pool.sql. Additive: no existing view changes.
--
-- Everything here reads pool_samples, a count of gateways per state taken every
-- POOL_SAMPLE_INTERVAL seconds.
--
-- What costs is the VM, not the container. The state vocabulary says so:
-- `created` is a VM provisioned whose container has been stopped, `deleted` is
-- a VM torn down. So a gateway reporting `free` is a VM that exists and is
-- billed — it simply is not running anything.
--
--   free     VM up, container stopped        -> billed, serves nothing
--   idle     VM up, container running, no call -> billed, serves nothing
--   ivr      caller on the IVR, no room yet  -> billed, serves
--   in_call  conference joined               -> billed, serves
--
-- Hence three quantities, and only the first is a cost:
--
--   provisioned = free + idle + ivr + in_call   every VM that exists
--   busy        = ivr + in_call                 what is served
--   spare       = free + idle                   provisioned and serving nothing
--
-- `running` (idle + ivr + in_call) is kept as a secondary figure. It says how
-- much of the pool was warm — a readiness indicator, useful for judging how
-- fast a call could be taken — but it is not the cost basis, and utilisation
-- computed against it flatters the result.
--
-- Out of scope, deliberately: the scaler's planned floor (unlockedMin, maxGw,
-- loadMax) lives in deploy/scaler/config/scaler.json and is not reachable from
-- here. These views say what happened, not whether it matched the plan.

-- The columns of these views changed name and order when the cost basis moved
-- from containers to VMs. CREATE OR REPLACE cannot rename or reorder columns,
-- so they are dropped first. monthly_pool_cost (schema_rates.sql) reads
-- monthly_pool_hours, and PostgreSQL will not drop a view another one reads:
-- it goes first, and schema_rates.sql, applied after this file, recreates it.
DROP VIEW IF EXISTS monthly_pool_cost;
DROP VIEW IF EXISTS pool_profile;
DROP VIEW IF EXISTS monthly_pool_hours;
DROP VIEW IF EXISTS pool_pressure;

-- One label per sample: its weekday, and its group as the scaler names them
-- (default = Monday to Friday; Saturday and Sunday are their own group). The
-- three hour-by-day-type views read this and aggregate on both at once with
-- GROUPING SETS, so a working-days percentile is computed over every
-- working-day sample rather than averaged from five weekday percentiles.
-- OR REPLACE, never dropped: hourly_concurrency (lot2) reads it too.
CREATE OR REPLACE VIEW pool_sample_days AS
SELECT ts,
       date_trunc('month', ts)                                     AS month,
       ts::date                                                    AS day,
       lower(trim(to_char(ts, 'day')))                             AS weekday,
       CASE WHEN extract(isodow FROM ts) <= 5 THEN 'default' END   AS day_group,
       extract(hour FROM ts)::int                                  AS hour,
       free, idle, ivr, in_call, interval_s
FROM pool_samples;

-- The same rows for one period. The filter reaches pool_samples.ts, and its
-- primary key index, before any grouping happens.
CREATE OR REPLACE FUNCTION pool_sample_days_between(p_since timestamptz, p_until timestamptz)
RETURNS SETOF pool_sample_days LANGUAGE sql STABLE AS $$
    SELECT * FROM pool_sample_days WHERE ts >= p_since AND ts < p_until
$$;

-- Occupancy profile by time slot and day type -------------------------------
--
-- Day type mirrors how the scaler is configured (default / saturday / sunday),
-- so a reading translates into the same vocabulary as the setting it informs.
--
-- Averages say what it cost; the peak and p95 say whether it sufficed. Both are
-- needed: an hour averaging two gateways but peaking at nine has been sized for
-- nine, and the average alone would suggest cutting.

-- The period is a parameter so that samples are filtered BEFORE they are
-- aggregated: filtered after, on the view, every page read the whole
-- history (3.9 s for a month once a year of samples is stored).
-- One function, two groupings. Over a period (the console), a slot is one
-- row whatever the number of months the period spans: grouped by month too,
-- a year gave twelve rows per hour, and the chart kept one of them at
-- random. By month (the whole-history view, the restore check), month
-- says which one; over a period it is NULL.
CREATE OR REPLACE FUNCTION pool_profile_rows(p_since timestamptz, p_until timestamptz, p_by_month boolean)
RETURNS TABLE (
    month timestamptz,
    day_type text,
    hour integer,
    provisioned_avg numeric,
    provisioned_peak integer,
    busy_avg numeric,
    busy_peak integer,
    busy_p95 numeric,
    spare_avg numeric,
    spare_peak integer,
    running_avg numeric,
    free_avg numeric,
    utilisation_pct numeric,
    samples bigint,
    days bigint
) LANGUAGE sql STABLE AS $$
SELECT m AS month,
       COALESCE(weekday, day_group)                              AS day_type,
       hour,

       -- what it costs: every VM that exists
       ROUND(AVG(free + idle + ivr + in_call), 2)                AS provisioned_avg,
       MAX(free + idle + ivr + in_call)                          AS provisioned_peak,

       -- what it serves
       ROUND(AVG(ivr + in_call), 2)                              AS busy_avg,
       MAX(ivr + in_call)                                        AS busy_peak,
       ROUND(percentile_cont(0.95) WITHIN GROUP (ORDER BY ivr + in_call)::numeric, 2)
                                                                 AS busy_p95,

       -- the lever: provisioned and serving nothing
       ROUND(AVG(free + idle), 2)                                AS spare_avg,
       MAX(free + idle)                                          AS spare_peak,

       -- how much of the pool was warm: readiness, not cost
       ROUND(AVG(idle + ivr + in_call), 2)                       AS running_avg,
       ROUND(AVG(free), 2)                                       AS free_avg,

       -- share of provisioned time actually spent serving
       ROUND(100.0 * SUM(ivr + in_call)
             / NULLIF(SUM(free + idle + ivr + in_call), 0), 1)   AS utilisation_pct,

       COUNT(*)                                                  AS samples,
       -- how many distinct days the slot was read on: a weekday over one
       -- month is four or five, and a peak taken on that few says so
       COUNT(DISTINCT day)                                       AS days
FROM (SELECT *, CASE WHEN p_by_month THEN month END AS m
        FROM pool_sample_days_between(p_since, p_until)) s
GROUP BY GROUPING SETS ((m, weekday, hour), (m, day_group, hour))
-- The group set has no group for a weekend sample: that row is dropped, and
-- Saturday and Sunday exist once, as their own day.
HAVING COALESCE(weekday, day_group) IS NOT NULL
$$;

CREATE OR REPLACE FUNCTION pool_profile_between(p_since timestamptz, p_until timestamptz)
RETURNS TABLE (
    month timestamptz,
    day_type text,
    hour integer,
    provisioned_avg numeric,
    provisioned_peak integer,
    busy_avg numeric,
    busy_peak integer,
    busy_p95 numeric,
    spare_avg numeric,
    spare_peak integer,
    running_avg numeric,
    free_avg numeric,
    utilisation_pct numeric,
    samples bigint,
    days bigint
) LANGUAGE sql STABLE AS $$
    SELECT * FROM pool_profile_rows(p_since, p_until, false)
$$;

-- The whole history, for reading by hand and for the restore check. The
-- console calls pool_profile_between() with its period.
CREATE VIEW pool_profile AS SELECT * FROM pool_profile_rows('-infinity', 'infinity', true);

COMMENT ON VIEW pool_profile IS
    'Gateway occupancy by month, day type and hour — day type is a weekday '
    '(monday … sunday) or a group (default = Monday to Friday). provisioned = every VM that '
    'exists (the cost basis, free included), busy = ivr+in_call (what serves), '
    'spare = the gap between the two. running counts warm containers only and is '
    'a readiness indicator, never the denominator of utilisation.';

-- Hours per month, by what the gateway was doing -----------------------------
--
-- Same numbers integrated over time rather than averaged, so they can be read
-- as a cost and compared month to month.

CREATE VIEW monthly_pool_hours AS
SELECT date_trunc('month', ts)                                        AS month,
       ROUND(SUM(free * interval_s) / 3600.0, 1)                      AS free_hours,
       ROUND(SUM(idle * interval_s) / 3600.0, 1)                      AS idle_hours,
       ROUND(SUM(ivr * interval_s) / 3600.0, 1)                       AS ivr_hours,
       ROUND(SUM(in_call * interval_s) / 3600.0, 1)                   AS call_hours,
       -- the billable total: every VM-hour, whatever the container was doing
       ROUND(SUM((free + idle + ivr + in_call) * interval_s) / 3600.0, 1)
                                                                      AS provisioned_hours,
       ROUND(SUM((idle + ivr + in_call) * interval_s) / 3600.0, 1)    AS running_hours,
       ROUND(100.0 * SUM((ivr + in_call) * interval_s)
             / NULLIF(SUM((free + idle + ivr + in_call) * interval_s), 0), 1)
                                                                      AS utilisation_pct,
       MAX(free + idle + ivr + in_call)                               AS provisioned_peak,
       MAX(ivr + in_call)                                             AS busy_peak,
       COUNT(*)                                                       AS samples,
       -- Coverage: a gap in sampling under-counts hours silently, so the number
       -- of samples is published next to the hours it produced.
       ROUND(100.0 * COUNT(*) * MAX(interval_s)
             / NULLIF(EXTRACT(epoch FROM (
                   LEAST(date_trunc('month', ts) + interval '1 month', now())
                   - date_trunc('month', ts))), 0), 1)                AS coverage_pct
FROM pool_samples
GROUP BY 1;

COMMENT ON VIEW monthly_pool_hours IS
    'VM-hours per month by state. provisioned_hours is the billable total, free '
    'included: a stopped container still sits on a VM that exists. coverage_pct '
    'is the share of the month actually sampled — a Manager that was down '
    'under-counts, and this says by how much.';

-- Saturation -----------------------------------------------------------------
--
-- Without the scaler's ceiling we cannot say "maxGw was reached". What we can
-- say is when nothing was left to take a new call: no warm container and no
-- provisioned VM to start one on. At that moment a caller waits for a VM to be
-- created, which is the slow path.
--
-- A free VM is deliberately counted as spare here, unlike in the cost views: it
-- costs like any other, but it can take a call in the time a container starts.
--
-- It is not the same thing as a refusal — the scaler may well have kept up —
-- but it is the only saturation signal available from measurement alone, and it
-- is the one that justifies raising the floor.

-- The period is a parameter so that samples are filtered BEFORE they are
-- aggregated: filtered after, on the view, every page read the whole
-- history (3.9 s for a month once a year of samples is stored).
-- One function, two groupings. Over a period (the console), a slot is one
-- row whatever the number of months the period spans: grouped by month too,
-- a year gave twelve rows per hour, and the chart kept one of them at
-- random. By month (the whole-history view, the restore check), month
-- says which one; over a period it is NULL.
CREATE OR REPLACE FUNCTION pool_pressure_rows(p_since timestamptz, p_until timestamptz, p_by_month boolean)
RETURNS TABLE (
    month timestamptz,
    day_type text,
    hour integer,
    samples bigint,
    no_spare_samples bigint,
    no_spare_pct numeric,
    no_spare_minutes numeric,
    cold_start_minutes numeric,
    days bigint
) LANGUAGE sql STABLE AS $$
SELECT m AS month,
       COALESCE(weekday, day_group)                               AS day_type,
       hour,
       COUNT(*)                                                   AS samples,
       COUNT(*) FILTER (WHERE free = 0 AND idle = 0 AND (ivr + in_call) > 0)
                                                                  AS no_spare_samples,
       ROUND(100.0 * COUNT(*) FILTER (WHERE free = 0 AND idle = 0 AND (ivr + in_call) > 0)
             / NULLIF(COUNT(*), 0), 1)                            AS no_spare_pct,
       ROUND(SUM(interval_s) FILTER (WHERE free = 0 AND idle = 0 AND (ivr + in_call) > 0) / 60.0, 1)
                                                                  AS no_spare_minutes,
       -- warm containers exhausted but a VM was available: a call could still
       -- be taken, only more slowly.
       ROUND(SUM(interval_s) FILTER (WHERE idle = 0 AND free > 0 AND (ivr + in_call) > 0) / 60.0, 1)
                                                                  AS cold_start_minutes,
       COUNT(DISTINCT day)                                        AS days
FROM (SELECT *, CASE WHEN p_by_month THEN month END AS m
        FROM pool_sample_days_between(p_since, p_until)) s
GROUP BY GROUPING SETS ((m, weekday, hour), (m, day_group, hour))
-- The group set has no group for a weekend sample: that row is dropped, and
-- Saturday and Sunday exist once, as their own day.
HAVING COALESCE(weekday, day_group) IS NOT NULL
$$;

CREATE OR REPLACE FUNCTION pool_pressure_between(p_since timestamptz, p_until timestamptz)
RETURNS TABLE (
    month timestamptz,
    day_type text,
    hour integer,
    samples bigint,
    no_spare_samples bigint,
    no_spare_pct numeric,
    no_spare_minutes numeric,
    cold_start_minutes numeric,
    days bigint
) LANGUAGE sql STABLE AS $$
    SELECT * FROM pool_pressure_rows(p_since, p_until, false)
$$;

-- The whole history, for reading by hand and for the restore check. The
-- console calls pool_pressure_between() with its period.
CREATE VIEW pool_pressure AS SELECT * FROM pool_pressure_rows('-infinity', 'infinity', true);

COMMENT ON VIEW pool_pressure IS
    'Time spent with nothing left to take a new call — no warm container and no '
    'provisioned VM — while calls were running. cold_start_minutes covers the '
    'milder case where a VM was free but nothing warm. Neither is a refusal, but '
    'both justify raising the floor for that slot.';
