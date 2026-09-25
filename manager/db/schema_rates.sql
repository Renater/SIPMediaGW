-- Gateway Manager — the cost of a gateway over time
--
-- DECOMMISSIONED (P19): nothing reads vm_rates or monthly_pool_cost any more.
-- The cost in euros left out the fixed infrastructure and the services around
-- it, and was read as the cost of the service; the Manager reports VM-hours.
-- Both objects are kept so that the rates already entered survive, and will be
-- dropped by a later lot once the decision is confirmed.
--
-- Apply after schema_pool.sql.
--
-- A single rate in `settings` was wrong the moment the price changed: October
-- 2026 recomputed with the 2027 rate would show a cost nobody was ever billed,
-- and a report reissued a year later would contradict the one that was sent.
--
-- Rates are dated instead. A month is costed with the rate in force that month,
-- so the past stays what it was.

CREATE TABLE IF NOT EXISTS vm_rates (
    valid_from  DATE PRIMARY KEY,
    hourly_cost NUMERIC(10, 4) NOT NULL CHECK (hourly_cost >= 0),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by  TEXT NOT NULL DEFAULT current_user
);

COMMENT ON TABLE vm_rates IS
    'Hourly cost of a VM, by the date it takes effect. A month is costed with '
    'the rate in force that month: reissuing a past report must give the figure '
    'that was sent, not the figure today''s price would produce.';

-- Carry over a rate already entered as a flat setting, effective from the
-- oldest month that has samples: before dating existed, that is the period it
-- was implicitly meant to cover.
-- The table this reads from was superseded by vm_rates and is no longer
-- created: the carry-over only runs where it still exists.
DO $$
BEGIN
    IF to_regclass('settings') IS NOT NULL THEN
        INSERT INTO vm_rates (valid_from, hourly_cost)
        SELECT COALESCE((SELECT MIN(ts)::date FROM pool_samples), CURRENT_DATE),
               value::numeric
        FROM settings WHERE key = 'vm_hourly_cost'
        ON CONFLICT (valid_from) DO NOTHING;
    END IF;
END $$;

-- Monthly cost, each month at its own rate.
DROP VIEW IF EXISTS monthly_pool_cost;
CREATE VIEW monthly_pool_cost AS
SELECT h.month,
       h.provisioned_hours,
       h.call_hours,
       -- Hours carrying no conference: the part that buys nothing, and the one
       -- that makes the case for adjusting the floor.
       GREATEST(h.provisioned_hours - h.call_hours, 0)                AS idle_paid_hours,
       r.hourly_cost,
       ROUND(h.provisioned_hours * r.hourly_cost, 2)                  AS cost,
       ROUND(GREATEST(h.provisioned_hours - h.call_hours, 0) * r.hourly_cost, 2)
                                                                      AS idle_cost
FROM monthly_pool_hours h
LEFT JOIN LATERAL (
    SELECT hourly_cost FROM vm_rates
     WHERE valid_from <= (h.month + interval '1 month' - interval '1 day')::date
     ORDER BY valid_from DESC LIMIT 1
) r ON TRUE;

COMMENT ON VIEW monthly_pool_cost IS
    'Cost per month at the rate in force that month. cost is null for months '
    'before the first rate: showing zero would read as free.';
