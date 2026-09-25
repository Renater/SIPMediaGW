"""
The user table: who can sign in, with what role, and since when.

One module owns the SQL of manager_users and user_audit; auth.py decides
what a password must look like and whether a session is still good, the
routes in api/users.py decide who may do what. Tests replace this module's
functions with an in-memory store, so nothing else in the code base needs a
database to exercise accounts.

Every account carries a `session_epoch`. A session records the epoch it was
opened under; changing the password, the role, or disabling the account bumps
it, and every other session of that account is refused on its next request.
That is what a password change after a leak is for. A deleted account has no
row to match: its sessions end the same way. Signing out bumps it too: the
cookie is signed, not stored, so a copy of it would otherwise outlive the
sign-out.

A change made from the console and its line in user_audit are written in one
transaction (the `audit` argument): a change is never kept without its line,
nor a line without its change.
"""

import json
import logging

from psycopg import sql
from psycopg.rows import dict_row

from db import connection, execute, fetch

log = logging.getLogger("manager.users")

ROLES = ("admin", "operator")
SOURCES = ("local", "proconnect")

# Composed with psycopg.sql rather than formatted into the text: the column
# names are identifiers the driver quotes, and no query here is assembled from
# strings (bandit B608, the audit's mgr-sql-built-by-hand).
COLUMN_NAMES = ("id", "username", "first_name", "last_name", "role", "source", "external_id",
                "password_hash", "must_change_password", "enabled", "session_epoch", "created_at",
                "created_by", "password_changed_at", "last_login_at", "updated_at")
COLUMNS = sql.SQL(", ").join(sql.Identifier(name) for name in COLUMN_NAMES)


def withColumns(query: str) -> sql.Composed:
    """The query with {columns} standing for the account columns."""
    return sql.SQL(query).format(columns=COLUMNS)


AUDIT_INSERT = """
    INSERT INTO user_audit (actor, action, target, detail)
    VALUES (%s, %s, %s, %s)
"""


def _write(query, params, audit=None):
    """
    A write and, when `audit` is given as (actor, action, target, detail), its
    audit line, in one transaction. The line is written only if the write
    touched a row: an update of a vanished account leaves no trace of a change
    that did not happen.
    """
    with connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query, params)
            rows = cursor.fetchall() if cursor.description else []
            if audit and rows:
                actor, action, target, detail = audit
                cursor.execute(AUDIT_INSERT, (actor, action, target, json.dumps(detail or {})))
    return rows


def getUser(username: str):
    """The account row, or None. Names are stored lower-case."""
    rows = fetch(withColumns("SELECT {columns} FROM manager_users WHERE username = %s"), (username.lower(),))
    return rows[0] if rows else None


def listUsers():
    return fetch(withColumns("SELECT {columns} FROM manager_users ORDER BY role, username"))


def countUsers() -> int:
    return fetch("SELECT COUNT(*) AS n FROM manager_users")[0]["n"]


def countActiveAdmins() -> int:
    return fetch("""
        SELECT COUNT(*) AS n FROM manager_users WHERE role = 'admin' AND enabled
    """)[0]["n"]


def createUser(username: str, role: str, source: str, passwordHash, createdBy: str,
               mustChange: bool = True, externalId=None, firstName=None, lastName=None, audit=None):
    rows = _write(withColumns("""
        INSERT INTO manager_users (username, first_name, last_name, role, source, external_id,
                                   password_hash, must_change_password, created_by)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING {columns}
    """), (username.lower(), firstName, lastName, role, source, externalId, passwordHash, mustChange, createdBy),
        audit)
    return rows[0]


def setPassword(username: str, passwordHash: str, mustChange: bool, audit=None):
    """A new hash, and a new epoch: every other session of the account ends."""
    rows = _write(withColumns("""
        UPDATE manager_users
           SET password_hash = %s, must_change_password = %s,
               password_changed_at = now(), updated_at = now(),
               session_epoch = session_epoch + 1
         WHERE username = %s
        RETURNING {columns}
    """), (passwordHash, mustChange, username.lower()), audit)
    return rows[0] if rows else None


def updateAccount(username: str, name=None, role=None, enabled=None, audit=None):
    """
    The changes an administrator makes in one go — name (first, last), role,
    state — as one statement with its audit line. A role or a state change
    bumps the epoch; a name alone does not. The SET list is assembled from the
    fixed fragments below only; the values travel as parameters.
    """
    sets, params = [], []
    if name is not None:
        sets.append("first_name = %s, last_name = %s")
        params.extend(name)
    if role is not None:
        sets.append("role = %s")
        params.append(role)
    if enabled is not None:
        sets.append("enabled = %s")
        params.append(enabled)
    if role is not None or enabled is not None:
        sets.append("session_epoch = session_epoch + 1")
    if not sets:
        return getUser(username)
    query = sql.SQL("UPDATE manager_users SET {sets}, updated_at = now() "
                    "WHERE username = %s RETURNING {columns}").format(
        sets=sql.SQL(", ").join(map(sql.SQL, sets)), columns=COLUMNS)
    rows = _write(query, (*params, username.lower()), audit)
    return rows[0] if rows else None


def bumpEpoch(username: str):
    """Every session of the account ends: what signing out does."""
    execute("UPDATE manager_users SET session_epoch = session_epoch + 1 WHERE username = %s",
            (username.lower(),))


def touchLogin(username: str):
    """Recorded at sign-in only; read back as 'last sign-in' in the user list."""
    execute("UPDATE manager_users SET last_login_at = now() WHERE username = %s", (username.lower(),))


def deleteUser(username: str, audit=None) -> bool:
    """The row goes; user_audit keeps every line that names the account."""
    rows = _write("DELETE FROM manager_users WHERE username = %s RETURNING id", (username.lower(),), audit)
    return bool(rows)

