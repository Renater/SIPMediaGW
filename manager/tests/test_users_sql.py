"""
users.py composes its queries with psycopg.sql: no account query is
assembled from strings any more. Rendered here without a database, so a
mistake in the composition fails in the suite rather than at the first sign-in.
"""

import pytest

sql = pytest.importorskip("psycopg.sql")

import users   # noqa: E402


@pytest.fixture
def captured(monkeypatch):
    queries = []

    def record(query, params=(), audit=None):
        queries.append((query.as_string(None), tuple(params)))
        return [{"username": "a@x.fr"}]

    monkeypatch.setattr(users, "_write", record)
    monkeypatch.setattr(users, "fetch", record)
    return queries


def test_the_columns_are_quoted_identifiers(captured):
    users.getUser("A@x.fr")
    text, params = captured[-1]
    assert text.startswith('SELECT "id", "username", "first_name"')
    assert text.endswith("FROM manager_users WHERE username = %s") and params == ("a@x.fr",)
    users.listUsers()
    assert captured[-1][0].endswith("ORDER BY role, username")


def test_an_update_sets_only_what_changes(captured):
    users.updateAccount("A@x.fr", name=("Ann", "Bee"), role="admin")
    text, params = captured[-1]
    assert text.startswith("UPDATE manager_users SET first_name = %s, last_name = %s, role = %s, "
                           "session_epoch = session_epoch + 1, updated_at = now() WHERE username = %s")
    assert text.count("%s") == len(params) == 4
    users.updateAccount("A@x.fr", name=("Ann", "Bee"))
    assert "session_epoch" not in captured[-1][0].split("RETURNING")[0], "a name alone ends no session"


@pytest.mark.parametrize("call", [
    lambda: users.createUser("a@x.fr", "operator", "local", "h", "t"),
    lambda: users.setPassword("a@x.fr", "h", True),
])
def test_writes_return_the_account(captured, call):
    call()
    text, params = captured[-1]
    assert 'RETURNING "id", "username"' in text and text.count("%s") == len(params)
