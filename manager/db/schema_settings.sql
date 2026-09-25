-- Gateway Manager — settings
--
-- A key/value store for the handful of figures the tool needs but cannot
-- measure: today, the hourly cost of a VM. It lives in the database rather than
-- in the environment because it is an organisational figure, not a deployment
-- parameter: it is entered by whoever knows it, changes without a restart, and
-- must read the same for everyone. A browser-side store would give each person
-- their own cost, which is worse than having none.
--
-- The same table is where the scaler's planned floor will land when the scaler
-- exposes it.

BEGIN;

CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_by TEXT NOT NULL DEFAULT current_user
);

COMMENT ON TABLE settings IS
    'Figures the tool cannot measure and someone has to supply. Values are kept '
    'as text and parsed by the caller: a setting is read far less often than it '
    'is argued about, and text keeps the table indifferent to what comes next.';

COMMIT;
