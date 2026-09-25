-- One-off: remove the objects the pivots left behind.
--
-- Eight views nobody reads and a table superseded the day it was created.
-- Their definitions are gone from the schema files, so a fresh database never
-- has them; this removes them from an existing one. Run once per deployment.
--
-- close_reasons stays: it is read by hand in psql.

BEGIN;
DROP VIEW IF EXISTS monthly_concurrency;
DROP VIEW IF EXISTS daily_concurrency;
DROP VIEW IF EXISTS monthly_service_sessions;
DROP VIEW IF EXISTS ivr_only_reasons;
DROP VIEW IF EXISTS monthly_consumption;
DROP VIEW IF EXISTS monthly_usage_by_platform;
DROP VIEW IF EXISTS org_unit_platform_mix;
DROP VIEW IF EXISTS usage_by_org_unit;
DROP TABLE IF EXISTS settings;
COMMIT;
