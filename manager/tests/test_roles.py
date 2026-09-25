"""Roles and sessions: an operator reads, an admin writes, and the form names nobody.

Accounts come from an in-memory store standing in for users.py, so these run
without a database; test_users_db.py plays the same scenarios against a real one.
"""

import datetime as dt

import pytest
from fastapi.testclient import TestClient

import app as application
import auth
import users
from tests.test_api_routes import Recorder, SAMPLE_ROW, routeModules


ALICE = "alice@sample.org"
# Any signed-in user reads this; only an admin creates an account. The VM
# rate routes played both parts until the cost was decommissioned (P19).
READ = "/api/reporting/recomputes"
BOB = {"username": "bob@sample.org", "first_name": "Bob", "last_name": "Martin",
       "role": "operator", "source": "local", "password": "bob-test-test-test"}   # a test value, never a real password


class MemoryUsers:
    """users.py without the database: the same functions over a dict."""

    def __init__(self):
        self.rows = {}
        self.log = []

    def _row(self, name):
        return dict(self.rows[name]) if name in self.rows else None

    def getUser(self, username):
        return self._row(username.lower())

    def listUsers(self):
        return [dict(r) for r in sorted(self.rows.values(), key=lambda r: (r["role"], r["username"]))]

    def countUsers(self):
        return len(self.rows)

    def countActiveAdmins(self):
        return sum(1 for r in self.rows.values() if r["role"] == "admin" and r["enabled"])

    def _audit(self, audit):
        """The audit line that users.py writes in the write's own transaction."""
        if audit:
            self.audit(*audit)

    def createUser(self, username, role, source, passwordHash, createdBy, mustChange=True, externalId=None,
                   firstName=None, lastName=None, audit=None):
        name = username.lower()
        assert name not in self.rows
        self.rows[name] = {
            "id": len(self.rows) + 1, "username": name, "first_name": firstName, "last_name": lastName,
            "role": role, "source": source, "last_login_at": None,
            "external_id": externalId, "password_hash": passwordHash,
            "must_change_password": mustChange, "enabled": True, "session_epoch": 0,
            "created_at": dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc), "created_by": createdBy,
            "password_changed_at": None, "updated_at": dt.datetime(2026, 9, 1, tzinfo=dt.timezone.utc),
        }
        self._audit(audit)
        return self._row(name)

    def _bump(self, name, **changes):
        row = self.rows.get(name.lower())
        if not row:
            return None
        row.update(changes)
        row["session_epoch"] += 1
        return self._row(name.lower())

    def setPassword(self, username, passwordHash, mustChange, audit=None):
        row = self._bump(username, password_hash=passwordHash, must_change_password=mustChange,
                         password_changed_at=dt.datetime.now(dt.timezone.utc))
        if row:
            self._audit(audit)
        return row

    def updateAccount(self, username, name=None, role=None, enabled=None, audit=None):
        row = self.rows.get(username.lower())
        if not row:
            return None
        if name is not None:
            row.update(first_name=name[0], last_name=name[1])
        if role is not None:
            row["role"] = role
        if enabled is not None:
            row["enabled"] = enabled
        if role is not None or enabled is not None:
            row["session_epoch"] += 1
        self._audit(audit)
        return self._row(username.lower())

    def bumpEpoch(self, username):
        self._bump(username)

    def setRole(self, username, role):
        return self._bump(username, role=role)

    def setEnabled(self, username, enabled):
        return self._bump(username, enabled=enabled)

    def setName(self, username, firstName, lastName):
        row = self.rows[username.lower()]
        row.update(first_name=firstName, last_name=lastName)
        return self._row(username.lower())

    def touchLogin(self, username):
        self.rows[username.lower()]["last_login_at"] = dt.datetime.now(dt.timezone.utc)

    def deleteUser(self, username, audit=None):
        gone = self.rows.pop(username.lower(), None) is not None
        if gone:
            self._audit(audit)
        return gone

    def audit(self, actor, action, target, detail=None):
        self.log.append((actor, action, target, detail or {}))

    def listAudit(self, limit=100):
        return [{"actor": a, "action": b, "target": c, "detail": d} for a, b, c, d in self.log[-limit:]]


@pytest.fixture()
def store(monkeypatch):
    """A store with an admin and an operator who have already changed their password."""
    memory = MemoryUsers()
    for name in ("getUser", "listUsers", "countUsers", "countActiveAdmins", "createUser",
                 "setPassword", "updateAccount", "bumpEpoch",
                 "touchLogin", "deleteUser", "audit", "listAudit"):
        monkeypatch.setattr(users, name, getattr(memory, name))
    memory.createUser("admin", "admin", "local", auth.hashPassword("root-secret-1234"), "test", mustChange=False)
    memory.createUser(ALICE, "operator", "local", auth.hashPassword("alice-secret-1234"), "test",
                      mustChange=False, firstName="Alice", lastName="Martin")
    monkeypatch.setattr(auth, "_failures", {})
    return memory


@pytest.fixture()
def accounts(store, monkeypatch):
    recorder = Recorder()
    recorder.rows = [SAMPLE_ROW]
    for module in routeModules():
        monkeypatch.setattr(module, "fetch", recorder, raising=False)
        monkeypatch.setattr(module, "execute", recorder, raising=False)
    return recorder


def signIn(client, username, password):
    return client.post("/auth/login", json={"username": username, "password": password})


def test_operator_reads_but_cannot_write(accounts):
    client = TestClient(application.app)
    assert signIn(client, ALICE, "alice-secret-1234").json()["role"] == "operator"
    assert client.get(READ).status_code == 200
    assert client.post("/api/users", json=BOB).status_code == 403
    assert client.delete(f"/api/users/{ALICE}").status_code == 403
    assert client.get("/api/users").status_code == 403
    assert client.get("/api/me").json()["role"] == "operator"


def test_admin_writes_and_is_recorded(accounts, store):
    client = TestClient(application.app)
    assert signIn(client, "admin", "root-secret-1234").json()["role"] == "admin"
    assert client.post("/api/users", json=BOB).status_code == 201
    # The actor is the signed-in user, not the database role.
    assert any(entry[:3] == ("admin", "create", BOB["username"]) for entry in store.log), store.log


def test_unknown_user_reads_like_a_wrong_password(accounts):
    client = TestClient(application.app)
    wrongPassword = signIn(client, ALICE, "nope")
    unknownUser = signIn(client, "carol", "nope")
    assert wrongPassword.status_code == unknownUser.status_code == 401
    assert wrongPassword.json() == unknownUser.json()


def test_missing_username_is_the_local_admin(accounts):
    """The old form sent no username; that request still means the admin."""
    client = TestClient(application.app)
    response = client.post("/auth/login", json={"password": "root-secret-1234"})
    assert response.status_code == 200 and response.json()["user"] == "admin"


def test_usernames_are_case_insensitive(accounts):
    client = TestClient(application.app)
    assert signIn(client, "Alice@Sample.org", "alice-secret-1234").status_code == 200


def test_a_disabled_account_cannot_sign_in_and_loses_its_session(accounts, store):
    client = TestClient(application.app)
    assert signIn(client, ALICE, "alice-secret-1234").status_code == 200
    assert client.get(READ).status_code == 200
    store.setEnabled(ALICE, False)
    assert client.get(READ).status_code == 401, "an open session survived the lock-out"
    assert client.get("/api/me").json()["authenticated"] is False
    assert signIn(client, ALICE, "alice-secret-1234").status_code == 401


def test_a_role_change_applies_on_the_next_request(accounts, store):
    """The role is the account's, not the cookie's."""
    client = TestClient(application.app)
    signIn(client, ALICE, "alice-secret-1234")
    assert client.post("/api/users", json=BOB).status_code == 403
    store.setRole(ALICE, "admin")
    # The epoch moved: the old session is out, a new sign-in carries the new role.
    assert client.get(READ).status_code == 401
    assert signIn(client, ALICE, "alice-secret-1234").json()["role"] == "admin"
    assert client.post("/api/users", json=BOB).status_code == 201


def test_an_empty_table_gets_the_default_admin(accounts, store, monkeypatch):
    """First sign-in ever: `admin` with the default password, to be changed at once."""
    store.rows.clear()
    monkeypatch.setattr(auth, "DEFAULT_PASSWORD", "manager123$")
    client = TestClient(application.app)
    response = signIn(client, "admin", "manager123$")
    assert response.status_code == 200 and response.json()["must_change_password"] is True
    assert ("bootstrap", "create", "admin", {"role": "admin", "source": "local"}) in store.log
    # Nothing else answers until the password is changed.
    assert client.get(READ).status_code == 403
    assert client.get(READ).json()["detail"] == "password change required"


def test_legacy_variables_create_no_account(accounts, store, monkeypatch):
    """MANAGER_PASSWORD and MANAGER_OPERATORS are gone: an empty table gets `admin`, nothing more."""
    store.rows.clear()
    monkeypatch.setenv("MANAGER_OPERATORS", "bob:bob-secret-1234")
    monkeypatch.setenv("MANAGER_PASSWORD", "old-shared-password")
    client = TestClient(application.app)
    assert signIn(client, "bob", "bob-secret-1234").status_code == 401
    assert signIn(client, "admin", "old-shared-password").status_code == 401
    assert sorted(store.rows) == ["admin"]


def test_legacy_variables_are_named_not_shown(monkeypatch):
    monkeypatch.delenv("MANAGER_PASSWORD", raising=False)
    monkeypatch.delenv("MANAGER_OPERATORS", raising=False)
    assert auth.legacyVariables() == []
    monkeypatch.setenv("MANAGER_OPERATORS", "bob:secret")
    assert auth.legacyVariables() == ["MANAGER_OPERATORS"]


def test_sign_in_is_recorded(accounts, store):
    """The list shows when an account last signed in; a password change is not a sign-in."""
    client = TestClient(application.app)
    assert store.rows[ALICE]["last_login_at"] is None
    signIn(client, ALICE, "alice-secret-1234")
    assert store.rows[ALICE]["last_login_at"] is not None
