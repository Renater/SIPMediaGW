-- Run once as the PostgreSQL superuser on the shared instance (Homer's container):
--   docker exec -i postgres psql -U <admin> -d postgres < bootstrap.sql
-- Replace the password before running; never commit it.
CREATE ROLE gw_manager LOGIN PASSWORD 'CHANGE_ME';
CREATE DATABASE gw_manager OWNER gw_manager;
-- then, as gw_manager on database gw_manager:
--   docker exec -i postgres psql -U gw_manager -d gw_manager < schema.sql
