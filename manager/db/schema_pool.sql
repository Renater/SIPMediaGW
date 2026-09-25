-- Manager — pool occupancy samples (gateway-hours for cost)
-- Apply after schema.sql, as gw_manager on database gw_manager.
--
-- Call logs cannot measure the cost of the pool: a pre-provisioned gateway
-- that waits for hours and never receives a call pushes nothing. The proxyAPI
-- sees every gateway's lifecycle (register -> unreachable), so the Manager
-- samples /admin/statuses at a fixed interval and integrates the counts.
--
-- What costs is the VM, not the container: free + idle + ivr + in_call. A
-- "free" slot is a VM that is up with no container running — billed, serving
-- nothing (schema_reporting_lot1.sql and the README spell out the states).

CREATE TABLE IF NOT EXISTS pool_samples (
    ts          TIMESTAMPTZ NOT NULL PRIMARY KEY,
    interval_s  INTEGER     NOT NULL,   -- seconds this sample stands for
    free        INTEGER     NOT NULL DEFAULT 0,
    idle        INTEGER     NOT NULL DEFAULT 0,
    ivr         INTEGER     NOT NULL DEFAULT 0,
    in_call     INTEGER     NOT NULL DEFAULT 0
);

-- daily_gateway_hours and monthly_gateway_hours were removed in favour of
-- pool_profile and monthly_pool_hours, in schema_reporting_lot1.sql.
--
-- They counted running containers — idle + ivr + in_call — as the cost. What is
-- billed is the VM, and a gateway reporting `free` is a VM that exists with its
-- container stopped. Keeping both meant two different answers to "what did the
-- pool cost", with nothing saying which one was right.
--
-- DROP VIEW IF EXISTS daily_gateway_hours;
-- DROP VIEW IF EXISTS monthly_gateway_hours;
-- Run those two once on an existing deployment; they are commented out so that
-- replaying this file on a fresh database does not fail on views that were
-- never created.
