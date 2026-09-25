"""
Played on the routes: writes from another
origin of the same site, sessions that never ended, account changes kept
without their audit line, and pushes whose shape answered 500.
"""

import time
import types

import pytest
from fastapi.testclient import TestClient

import app as application
import auth
import ingest.router as ingest
from tests.test_roles import ALICE, signIn


def signedIn(name, password):
    client = TestClient(application.app)
    assert signIn(client, name, password).status_code == 200
    return client


def test_a_cross_origin_write_is_refused_before_the_route(accounts):
    admin = signedIn("admin", "root-secret-1234")
    refused = admin.post("/api/org-units/recompute", headers={"Origin": "http://192.0.2.10",
                                                              "Sec-Fetch-Site": "same-site"})
    assert refused.status_code == 403
    assert admin.post("/api/users", json={}, headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
    # The same client, from its own origin, reaches the route (400: the body is empty).
    host = admin.base_url.host        # a str; .netloc is bytes in httpx
    reached = admin.post("/api/users", json={}, headers={"Origin": f"http://{host}", "Sec-Fetch-Site": "same-origin"})
    assert reached.status_code != 403


def test_sign_in_takes_json_only(accounts):
    """A form or text/plain body is what another page can post without asking."""
    client = TestClient(application.app)
    body = '{"username": "admin", "password": "root-secret-1234"}'
    assert client.post("/auth/login", content=body, headers={"Content-Type": "text/plain"}).status_code == 415
    assert client.post("/auth/login", content=body,
                       headers={"Content-Type": "application/json; charset=utf-8"}).status_code == 200


def test_signing_out_ends_the_other_sessions_of_the_account(accounts):
    """The cookie is signed, not stored: without the epoch, a copy outlived the sign-out."""
    here, elsewhere = signedIn(ALICE, "alice-secret-1234"), signedIn(ALICE, "alice-secret-1234")
    assert elsewhere.get("/api/me").json()["authenticated"] is True
    assert here.post("/auth/logout").status_code == 200
    assert elsewhere.get("/api/me").json()["authenticated"] is False
    assert signedIn(ALICE, "alice-secret-1234").get("/api/me").json()["authenticated"] is True


def test_a_session_ends_after_its_hours_however_busy(accounts, monkeypatch):
    client = signedIn(ALICE, "alice-secret-1234")
    assert client.get("/api/me").json()["authenticated"] is True
    later = time.time() + auth.SESSION_HOURS * 3600 + 60
    monkeypatch.setattr(auth, "time", types.SimpleNamespace(time=lambda: later, monotonic=time.monotonic))
    assert client.get("/api/me").json()["authenticated"] is False


def test_a_refused_change_writes_nothing(accounts, store):
    """The name used to be written, then the role refused: a change kept without its audit line."""
    admin = signedIn("admin", "root-secret-1234")
    lines = len(store.log)
    response = admin.put("/api/users/admin", json={"first_name": "Root", "last_name": "Admin", "role": "operator"})
    assert response.status_code == 409
    assert store.rows["admin"]["first_name"] is None, "the name was written before the refusal"
    assert len(store.log) == lines
    response = admin.put(f"/api/users/{ALICE}", json={"first_name": "Alicia", "role": "chief"})
    assert response.status_code == 400 and store.rows[ALICE]["first_name"] == "Alice"
    assert len(store.log) == lines


def test_one_audit_line_per_change_with_everything_in_it(accounts, store):
    admin = signedIn("admin", "root-secret-1234")
    response = admin.put(f"/api/users/{ALICE}", json={"first_name": "Alicia", "role": "admin", "enabled": False})
    assert response.status_code == 200
    assert store.log[-1] == ("admin", "update", ALICE, {"name": "Alicia Martin", "role": "admin", "enabled": False})


def test_a_wrong_password_is_logged_with_its_name(accounts, caplog):
    client = TestClient(application.app)
    signIn(client, "mallory\nforged line", "nope")
    line = next(r.getMessage() for r in caplog.records if "wrong password" in r.getMessage())
    assert "'mallory\\nforged line'" in line, "the name must be quoted, never a raw new line"


@pytest.fixture
def pushing(monkeypatch):
    monkeypatch.setattr(ingest, "ingestToken", "secret")
    return TestClient(application.app)


def test_a_token_with_foreign_characters_is_a_401(pushing):
    """compare_digest refused a non-ASCII str with a TypeError: a 500."""
    response = pushing.post("/ingest/calls", content=b"{}",
                            headers={"Authorization": "Bearer s\xe9cret".encode("latin-1"),
                                     "Content-Type": "application/json"})
    assert response.status_code == 401


@pytest.mark.parametrize("body", [
    b'{"call": {"details": {"callId": "a\\u0000b"}}}',
    b"[" * 100000 + b"]" * 100000,
    b'{"call": {"details": []}}',
])
def test_a_push_of_the_wrong_shape_is_a_400(pushing, body):
    response = pushing.post("/ingest/calls", content=body,
                            headers={"Authorization": "Bearer secret", "Content-Type": "application/json"})
    assert response.status_code == 400, response.text
