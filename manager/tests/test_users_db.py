"""
Accounts against a real database.

test_users.py plays the routes over an in-memory store; this file plays the
main scenarios over manager_users and user_audit themselves: the schema, its
checks, the epoch mechanics. Needs DATABASE_URL_TEST, skips without it.

On the lab database it leaves nothing behind: the accounts it creates carry a
marker in their name and are deleted at the end, audit lines included. One
exception: on an EMPTY user table the first sign-in creates `admin` with the
default password — which is what the first real sign-in would do too.
"""

import os

import pytest

DSN = os.getenv("DATABASE_URL_TEST")
MARKER = f"test-users-{os.getpid()}"
DOMAIN = "@test.invalid"
OP = f"{MARKER}-op{DOMAIN}"

pytestmark = pytest.mark.skipif(not DSN, reason="DATABASE_URL_TEST not set; needs a real database")


@pytest.fixture()
def client(monkeypatch):
    from fastapi.testclient import TestClient
    import auth
    import db
    import app as application

    monkeypatch.setattr(db, "databaseUrl", DSN)
    monkeypatch.setattr(db, "_pool", None)
    monkeypatch.setattr(auth, "_failures", {})
    yield TestClient(application.app)

    import psycopg
    with psycopg.connect(DSN) as conn, conn.cursor() as cursor:
        cursor.execute("DELETE FROM user_audit WHERE target LIKE %s", (f"{MARKER}%",))
        cursor.execute("DELETE FROM manager_users WHERE username LIKE %s", (f"{MARKER}%",))
        conn.commit()


@pytest.fixture()
def admin(client):
    """
    An administrator of this test's own: created straight in the table so the
    test never depends on the real admin's password, marked, deleted after.
    """
    import auth
    import users
    from fastapi.testclient import TestClient
    import app as application

    auth.ensureBootstrap()
    users.createUser(f"{MARKER}-admin{DOMAIN}", "admin", "local", auth.hashPassword("admin-of-the-test"),
                     "test", mustChange=False, firstName="Test", lastName="Admin")
    session = TestClient(application.app)
    response = session.post("/auth/login", json={"username": f"{MARKER}-admin{DOMAIN}", "password": "admin-of-the-test"})
    assert response.status_code == 200, response.json()
    return session


def test_create_sign_in_change_password(admin):
    from fastapi.testclient import TestClient
    import app as application

    name = OP
    created = admin.post("/api/users", json={"username": name, "first_name": "Op", "last_name": "Test",
                                             "role": "operator", "password": "initial-secret-1"})
    assert created.status_code == 201, created.json()

    op = TestClient(application.app)
    assert op.post("/auth/login", json={"username": name, "password": "initial-secret-1"}).json()["must_change_password"]
    assert op.get("/api/reporting/recomputes").status_code == 403
    changed = op.post("/api/account/password", json={"current": "initial-secret-1",
                                                     "new": "chosen by the operator", "confirm": "chosen by the operator"})
    assert changed.status_code == 200, changed.json()
    assert op.get("/api/reporting/recomputes").status_code == 200

    # The old password is gone, the new one works, the hash never travels.
    again = TestClient(application.app)
    assert again.post("/auth/login", json={"username": name, "password": "initial-secret-1"}).status_code == 401
    assert again.post("/auth/login", json={"username": name, "password": "chosen by the operator"}).status_code == 200
    listing = admin.get("/api/users").json()
    row = next(r for r in listing if r["username"] == name)
    assert row["must_change_password"] is False and "password_hash" not in row
    assert row["last_login_at"] is not None, "sign-in was not recorded"


def test_lock_out_ends_an_open_session(admin):
    from fastapi.testclient import TestClient
    import app as application

    name = f"{MARKER}-locked{DOMAIN}"
    admin.post("/api/users", json={"username": name, "first_name": "Locked", "last_name": "Test",
                                   "role": "operator", "password": "initial-secret-1"})
    op = TestClient(application.app)
    op.post("/auth/login", json={"username": name, "password": "initial-secret-1"})
    assert op.get("/api/me").json()["authenticated"] is True
    assert admin.put(f"/api/users/{name}", json={"enabled": False}).status_code == 200
    assert op.get("/api/me").json()["authenticated"] is False
    assert op.post("/auth/login", json={"username": name, "password": "initial-secret-1"}).status_code == 401


def test_audit_names_the_actor_and_never_a_secret(admin):
    name = f"{MARKER}-audited{DOMAIN}"
    admin.post("/api/users", json={"username": name, "first_name": "Audited", "last_name": "Test",
                                   "role": "operator", "password": "initial-secret-1"})
    admin.post(f"/api/users/{name}/password", json={"password": "reset-by-admin-1"})
    assert admin.delete(f"/api/users/{name}").status_code == 200
    lines = [line for line in admin.get("/api/users/audit").json() if line["target"] == name]
    assert [line["action"] for line in lines] == ["delete", "password.reset", "create"], "the audit outlives the account"
    assert all(line["actor"] == f"{MARKER}-admin{DOMAIN}" for line in lines)
    assert "initial-secret-1" not in str(lines) and "reset-by-admin-1" not in str(lines)


def test_the_schema_refuses_an_inconsistent_account(client):
    """A local account without a hash, or a ProConnect one with, is refused by the table itself."""
    import psycopg
    with psycopg.connect(DSN) as conn, conn.cursor() as cursor:
        with pytest.raises(psycopg.errors.CheckViolation):
            cursor.execute("INSERT INTO manager_users (username, role, source, created_by) VALUES (%s, 'operator', 'local', 'test')",
                           (f"{MARKER}-nohash{DOMAIN}",))
        conn.rollback()
        with pytest.raises(psycopg.errors.CheckViolation):
            cursor.execute("INSERT INTO manager_users (username, role, source, created_by) VALUES (%s, 'operator', 'proconnect', 'test')",
                           (f"{MARKER}-noid{DOMAIN}",))
        conn.rollback()
