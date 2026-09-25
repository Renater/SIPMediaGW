-- Gateway Manager — accounts
--
-- Before this file existed, accounts were configuration
-- (MANAGER_PASSWORD, MANAGER_OPERATORS): no password could be changed from
-- the console and no account created. auth.py fills an empty table with the
-- local admin and its default password, to be changed at first sign-in.
--
-- The username is an e-mail address for every account created from the
-- console; the bootstrap `admin` is the one exception, kept short so that the
-- way in never depends on a mailbox.

CREATE TABLE IF NOT EXISTS manager_users (
    id                   BIGSERIAL PRIMARY KEY,
    username             TEXT NOT NULL UNIQUE
                         CHECK (username = lower(username) AND username ~ '^[a-z0-9][a-z0-9._+@-]{1,63}$'),
    role                 TEXT NOT NULL CHECK (role IN ('admin', 'operator')),
    -- local: a password held here. proconnect: the identity provider signs
    -- the user in and external_id is its stable identifier; no password here.
    source               TEXT NOT NULL DEFAULT 'local' CHECK (source IN ('local', 'proconnect')),
    external_id          TEXT UNIQUE,
    password_hash        TEXT,
    must_change_password BOOLEAN NOT NULL DEFAULT true,
    enabled              BOOLEAN NOT NULL DEFAULT true,
    -- Bumped by a password change, a role change or a lock-out: a session
    -- opened under an older value is refused on its next request.
    session_epoch        INTEGER NOT NULL DEFAULT 0,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by           TEXT NOT NULL,
    password_changed_at  TIMESTAMPTZ,
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK ((source = 'local') = (password_hash IS NOT NULL)),
    CHECK ((source = 'proconnect') = (external_id IS NOT NULL))
);

-- Added after the first deployment: a person's name, and when they last
-- signed in. Empty for the bootstrap admin, required by the console form.
ALTER TABLE manager_users ADD COLUMN IF NOT EXISTS first_name TEXT;
ALTER TABLE manager_users ADD COLUMN IF NOT EXISTS last_name TEXT;
ALTER TABLE manager_users ADD COLUMN IF NOT EXISTS last_login_at TIMESTAMPTZ;

-- The first deployment's check did not allow `+` in an address. Replaced
-- rather than kept: an unnamed check gets this generated name.
ALTER TABLE manager_users DROP CONSTRAINT IF EXISTS manager_users_username_check;
ALTER TABLE manager_users ADD CONSTRAINT manager_users_username_check
    CHECK (username = lower(username) AND username ~ '^[a-z0-9][a-z0-9._+@-]{1,63}$');

COMMENT ON TABLE manager_users IS
    'Console accounts. Local accounts hold a scrypt hash; accounts from the '
    'identity provider hold its identifier and no password. A deleted account '
    'leaves the table; user_audit keeps its name.';

-- Who did what to which account. Names, roles and flags; never a secret. Not
-- a foreign key on purpose: the line outlives the account it names.
CREATE TABLE IF NOT EXISTS user_audit (
    id      BIGSERIAL PRIMARY KEY,
    at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor   TEXT NOT NULL,
    action  TEXT NOT NULL,
    target  TEXT NOT NULL,
    detail  JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS user_audit_at_idx ON user_audit (at DESC);
