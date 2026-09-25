-- One-off: remove the gateway-hours views, superseded by pool_profile and
-- monthly_pool_hours.
--
-- They measured running containers; the cost is the VM, free slots included.
-- Two views answering "what did the pool cost" with different numbers is worse
-- than one answering it imperfectly.
--
-- Run once per existing deployment. A fresh database never had them.

BEGIN;
DROP VIEW IF EXISTS daily_gateway_hours;
DROP VIEW IF EXISTS monthly_gateway_hours;
COMMIT;
