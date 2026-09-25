-- One-off: remove the cost objects.
--
-- The Manager once priced gateway hours in euros (a rates table and a monthly
-- cost view). The figure left out the fixed infrastructure and the services
-- around it, and was read as the cost of the service; the Manager reports
-- VM-hours instead. The definitions are gone from the schema files, so a
-- fresh database never has them; this removes them from an existing one.
-- Run once per deployment. The rates entered are lost: they are not used.

BEGIN;
DROP VIEW IF EXISTS monthly_pool_cost;
DROP TABLE IF EXISTS vm_rates;
DROP TABLE IF EXISTS settings;
-- Read by no route since the Usage summary sweeps the period's own calls.
DROP VIEW IF EXISTS daily_peak_concurrency;
COMMIT;
