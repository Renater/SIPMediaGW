"""
Database access shared by the read routes and the ingestion.

One connection pool for the process, a session time zone aligned with the
container, and a single place where psycopg errors are logged in full and
turned into a neutral exception: the client never sees SQL text.
"""

import logging
import os
import re
from contextlib import contextmanager

import psycopg
from psycopg import sql
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

log = logging.getLogger("manager.db")

databaseUrl = os.getenv("DATABASE_URL", "")

# Reporting periods are local, not UTC. SET TIME ZONE takes a literal, so the
# value is validated against a strict IANA-name pattern before interpolation.
sessionTimeZone = os.getenv("TZ", "Europe/Paris")
if not re.fullmatch(r"[A-Za-z][A-Za-z0-9_+-]*(/[A-Za-z0-9_+-]+)*", sessionTimeZone):
    log.warning("ignoring invalid TZ %r, using UTC", sessionTimeZone)
    sessionTimeZone = "UTC"


# A statement running longer than this is cancelled by the server: the route
# answers 503 and its pooled connection comes back, instead of being held for
# as long as the query runs — with five connections, five of those and every
# route waits. 0 disables it; a report that needs more is a query to fix.
statementTimeoutMs = int(os.getenv("DB_STATEMENT_TIMEOUT_MS", "30000"))
connectionOptions = f"-c timezone={sessionTimeZone} -c statement_timeout={statementTimeoutMs}"


class DatabaseUnavailable(Exception):
    """Raised to the API layer; mapped to a 503 with a generic message."""


_pool = None


def pool():
    global _pool
    if _pool is None:
        if not databaseUrl:
            raise DatabaseUnavailable("DATABASE_URL is not set")
        _pool = ConnectionPool(
            databaseUrl,
            min_size=1,
            max_size=int(os.getenv("DB_POOL_SIZE", "5")),
            timeout=5,
            # Session time zone set at connection level: date_trunc() and
            # ::date then bucket on local days. (A configure callback would
            # leave the connection in a transaction, which the pool rejects.)
            # `timeout` above bounds the wait for a pooled connection, not the
            # TCP connect: without connect_timeout a host that stopped answering
            # would hang a worker for the OS default, about two minutes.
            kwargs={"options": connectionOptions, "connect_timeout": 5},
            open=True,
        )
    return _pool


@contextmanager
def connection():
    """A pooled connection in a transaction; commits on success, rolls back on error."""
    try:
        with pool().connection() as conn:
            yield conn
    except psycopg.Error as exc:
        log.error("database error: %s", exc)
        raise DatabaseUnavailable("database error") from exc


def fetch(query, params=()):
    """Run a read query and return rows as dicts."""
    with connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query, params)
            return cursor.fetchall()


def execute(query, params=()):
    """
    Run a write and return whatever it RETURNING-ed, as dicts.

    Same mechanics as fetch(), under a name that says what it does: a reader
    looking for the places that change data should find them by name, not by
    reading every query. The transaction is the connection's — committed on
    success, rolled back on error.
    """
    with connection() as conn:
        with conn.cursor(row_factory=dict_row) as cursor:
            cursor.execute(query, params)
            return cursor.fetchall() if cursor.description else []


def sqlWith(text: str, **fragments: "str | sql.Composable") -> sql.Composed:
    """
    A query with {name} standing for fixed SQL fragments of the code (the scope
    of Usage and Quality, the Journal's filters). Composed by psycopg, not by
    string concatenation: the fragments are text the code wrote, the values
    still travel as %s parameters.
    """
    return sql.SQL(text).format(**{name: sql.SQL(fragment) if isinstance(fragment, str) else fragment
                                   for name, fragment in fragments.items()})
