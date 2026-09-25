"""Account management: own password, and what an administrator may do to others."""

import pytest
from fastapi.testclient import TestClient

import app as application
import auth
from tests.test_roles import ALICE, signIn

CAROL = "carol@sample.org"
NEW = {"username": CAROL, "first_name": "Carol", "last_name": "Durand", "role": "operator",
       "password": "initial-secret-1"}


@pytest.fixture()
def admin(accounts):
    client = TestClient(application.app)
    assert signIn(client, "admin", "root-secret-1234").status_code == 200
    return client


@pytest.fixture()
def alice(accounts):
    client = TestClient(application.app)
    assert signIn(client, ALICE, "alice-secret-1234").status_code == 200
    return client


def change(client, current, new, confirm=None):
    return client.post("/api/account/password",
                       json={"current": current, "new": new, "confirm": new if confirm is None else confirm})


# ------------------------------------------------------------- own password

def test_change_own_password_ends_the_other_sessions(alice, accounts, store):
    other = TestClient(application.app)
    signIn(other, ALICE, "alice-secret-1234")
    assert change(alice, "alice-secret-1234", "a brand new passphrase").status_code == 200
    assert alice.get("/api/reporting/recomputes").status_code == 200, "the session that changed it stays"
    assert other.get("/api/reporting/recomputes").status_code == 401, "the other session survived"
    assert signIn(TestClient(application.app), ALICE, "alice-secret-1234").status_code == 401
    assert signIn(TestClient(application.app), ALICE, "a brand new passphrase").status_code == 200
    assert store.log[-1][:3] == (ALICE, "password.change", ALICE)


def test_change_own_password_checks_everything(alice, monkeypatch):
    monkeypatch.setattr(auth, "MIN_PASSWORD_LENGTH", 11)
    assert change(alice, "wrong", "a brand new passphrase").status_code == 403
    assert change(alice, "alice-secret-1234", "a brand new passphrase", "another").status_code == 400
    assert change(alice, "alice-secret-1234", "short").status_code == 400
    assert change(alice, "alice-secret-1234", "alice-secret-1234").status_code == 400
    assert change(alice, "alice-secret-1234", ALICE.upper()).status_code == 400
    assert change(alice, "alice-secret-1234", "a brand new passphrase").status_code == 200


def test_wrong_current_password_counts_as_a_failed_attempt(alice):
    for _ in range(auth.maxFailures):
        assert change(alice, "wrong", "a brand new passphrase").status_code == 403
    assert signIn(TestClient(application.app), ALICE, "alice-secret-1234").status_code == 429


def test_a_forced_change_unlocks_the_console(admin, store):
    assert admin.post("/api/users", json=NEW).status_code == 201
    carol = TestClient(application.app)
    assert signIn(carol, CAROL, "initial-secret-1").json()["must_change_password"] is True
    assert carol.get("/api/reporting/recomputes").status_code == 403
    assert change(carol, "initial-secret-1", "carol picks her own").status_code == 200
    assert carol.get("/api/reporting/recomputes").status_code == 200
    assert carol.get("/api/me").json()["must_change_password"] is False


# ------------------------------------------------------------ administration

def test_admin_creates_a_local_account(admin, store):
    response = admin.post("/api/users", json={**NEW, "username": CAROL.upper()})
    assert response.status_code == 201, response.json()
    body = response.json()
    assert body["username"] == CAROL and body["must_change_password"] is True and "password_hash" not in body
    assert body["first_name"] == "Carol" and body["last_name"] == "Durand" and body["last_login_at"] is None
    assert ("admin", "create", CAROL, {"role": "operator", "source": "local", "name": "Carol Durand"}) in store.log
    assert admin.post("/api/users", json=NEW).status_code == 409


def test_create_validates_everything(admin):
    post = lambda **body: admin.post("/api/users", json={**NEW, **body}).status_code
    assert post(username="carol") == 400, "the username is an e-mail address"
    assert post(username="Carol Durand@x.fr") == 400
    assert post(first_name="") == 400
    assert post(last_name=" ") == 400
    assert post(role="root") == 400
    assert post(source="ldap") == 400
    assert post(source="proconnect") == 400, "not before the SSO integration"
    assert post(password="short") == 400
    assert post(password=CAROL) == 400
    assert post() == 201


def test_secrets_never_leave(admin):
    listing = admin.get("/api/users").json()
    assert listing and all("password_hash" not in row and "hash" not in str(row) for row in listing)


def test_reset_forces_a_change_and_ends_sessions(admin, alice, store):
    response = admin.post(f"/api/users/{ALICE}/password", json={"password": "reset-by-admin-1"})
    assert response.status_code == 200 and response.json()["must_change_password"] is True
    assert alice.get("/api/reporting/recomputes").status_code == 401
    fresh = TestClient(application.app)
    assert signIn(fresh, ALICE, "reset-by-admin-1").status_code == 200
    assert fresh.get("/api/reporting/recomputes").status_code == 403
    assert admin.post("/api/users/nobody@x.fr/password", json={"password": "reset-by-admin-1"}).status_code == 404
    assert store.log[-1][:3] == ("admin", "password.reset", ALICE)


def test_role_name_and_lock_out(admin, store):
    assert admin.put(f"/api/users/{ALICE}", json={"role": "admin"}).json()["role"] == "admin"
    assert admin.put(f"/api/users/{ALICE}", json={"enabled": False}).json()["enabled"] is False
    assert admin.put(f"/api/users/{ALICE}", json={"enabled": True}).json()["enabled"] is True
    renamed = admin.put(f"/api/users/{ALICE}", json={"first_name": "Alicia"}).json()
    assert (renamed["first_name"], renamed["last_name"]) == ("Alicia", "Martin")
    assert admin.put(f"/api/users/{ALICE}", json={"last_name": ""}).status_code == 400
    assert admin.put(f"/api/users/{ALICE}", json={"role": "chief"}).status_code == 400
    assert admin.put("/api/users/nobody@x.fr", json={"enabled": False}).status_code == 404
    assert [entry[1] for entry in store.log[-4:]] == ["update"] * 4


def test_nobody_touches_their_own_role_or_state(admin, store):
    """Own role, own state, own deletion: another administrator does that."""
    store.createUser("second@sample.org", "admin", "local", auth.hashPassword("second-secret-1"), "test",
                     mustChange=False)
    assert admin.put("/api/users/admin", json={"role": "operator"}).status_code == 409
    assert admin.put("/api/users/admin", json={"enabled": False}).status_code == 409
    assert admin.delete("/api/users/admin").status_code == 409
    # A name change on one's own account is fine.
    assert admin.put("/api/users/admin", json={"first_name": "Root", "last_name": "Admin"}).status_code == 200


def test_the_console_always_keeps_a_way_in(admin):
    """The last enabled administrator stays one, whoever asks."""
    admin.put(f"/api/users/{ALICE}", json={"role": "admin"})
    alice = TestClient(application.app)
    signIn(alice, ALICE, "alice-secret-1234")
    # alice demotes admin: allowed, she remains. Then nobody can demote, disable or delete her.
    assert alice.put("/api/users/admin", json={"role": "operator"}).status_code == 200
    root = TestClient(application.app)
    signIn(root, "admin", "root-secret-1234")
    assert root.get("/api/users").status_code == 403, "demoted on the next request"
    assert alice.put(f"/api/users/{ALICE}", json={"role": "operator"}).status_code == 409
    assert alice.put(f"/api/users/{ALICE}", json={"enabled": False}).status_code == 409
    assert alice.delete(f"/api/users/{ALICE}").status_code == 409


def test_delete_keeps_the_audit_and_ends_the_session(admin, alice, store):
    assert admin.delete(f"/api/users/{ALICE}").status_code == 200
    assert ALICE not in store.rows
    assert alice.get("/api/reporting/recomputes").status_code == 401, "a deleted account kept a session"
    assert signIn(TestClient(application.app), ALICE, "alice-secret-1234").status_code == 401
    assert store.log[-1][:3] == ("admin", "delete", ALICE)
    assert admin.delete(f"/api/users/{ALICE}").status_code == 404
    lines = [line for line in admin.get("/api/users/audit").json() if line["target"] == ALICE]
    assert lines, "the audit lost the deleted account"


def test_audit_is_readable_by_admins_only(admin, alice):
    assert admin.get("/api/users/audit").status_code == 200
    assert alice.get("/api/users/audit").status_code == 403
