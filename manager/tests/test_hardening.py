"""
P11 — what the production readiness review found in the request path.

A-01  no blocking call on the event loop from an `async def` route
A-02  the password change is throttled like the sign-in
A-03  a malformed sign-in body is a failed attempt, not a 500
A-04  a year outside 1970-2100 is a 400, not a 500
O-03  every connection carries a statement timeout
S-07  the browser never receives the proxyAPI's internal address
and: a sign-in lands on Supervision, a reload keeps the view.
"""

import ast
import asyncio
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

import app as application
import auth
from api import park
from api.periods import resolvePeriod
from tests.test_users import change

ROOT = Path(__file__).resolve().parent.parent

# Synchronous and slow: a database round trip or a scrypt. Called directly
# from an `async def` route they stop every other request while they run.
BLOCKING = {"fetch", "execute", "authenticate", "sessionAccount", "recordSignIn", "getUser",
            "listUsers", "hashPassword", "checkPassword", "touchLogin", "connection"}


def asyncRouteCalls(path):
    tree = ast.parse(path.read_text())
    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        routed = any(isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                     and d.func.attr in {"get", "post", "put", "delete"} for d in node.decorator_list)
        if not routed:
            continue
        for call in callsOutsideNestedFunctions(node):
            name = call.func.attr if isinstance(call.func, ast.Attribute) else getattr(call.func, "id", "")
            if name in BLOCKING:
                yield f"{path.name}:{call.lineno} {node.name}() calls {name}()"


def callsOutsideNestedFunctions(function):
    """
    The calls a route makes itself. A function defined inside it runs only
    where it is handed over — ingestion passes its store() to
    run_in_threadpool — so its body is not the route's.
    """
    pending = list(function.body)
    while pending:
        node = pending.pop()
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(node, ast.Call):
            yield node
        pending.extend(ast.iter_child_nodes(node))


def test_async_routes_never_block_the_event_loop():
    """A-01: on the loop, a slow database froze the park view and the sampler with it."""
    files = [ROOT / "app.py", ROOT / "ingest" / "router.py", *sorted((ROOT / "api").glob("*.py"))]
    offenders = [line for path in files for line in asyncRouteCalls(path)]
    assert not offenders, "blocking calls in async routes (use run_in_threadpool or def):\n" + "\n".join(offenders)


def test_the_password_change_is_throttled(alice):
    """A-02: failures were counted there but never read, so guessing went on unbounded."""
    for _ in range(auth.maxFailures):
        assert change(alice, "wrong", "a brand new passphrase").status_code == 403
    assert change(alice, "alice-secret-1234", "a brand new passphrase").status_code == 429


@pytest.mark.parametrize("body", ['[]', '"admin"', '42', '{"username": "admin", "password": 1}',
                                  '{"username": ["admin"], "password": null}'])
def test_a_malformed_sign_in_is_a_failed_attempt(accounts, body):
    """A-03: these answered 500 and did not count against the throttle."""
    client = TestClient(application.app)
    response = client.post("/auth/login", content=body, headers={"Content-Type": "application/json"})
    assert response.status_code == 401, response.text
    assert auth._failures, "the attempt was not counted"


@pytest.mark.parametrize("period", ["9999", "0000", "1969", "2101", "0000-01", "9999-12"])
def test_years_out_of_range_are_rejected(period):
    """A-04: date(10000, 1, 1) raised a ValueError, which answered 500."""
    with pytest.raises(HTTPException) as error:
        resolvePeriod(period)
    assert error.value.status_code == 400


def test_every_connection_has_a_statement_timeout():
    """O-03: a query that never ends held a pooled connection for good."""
    import db
    assert f"statement_timeout={db.statementTimeoutMs}" in db.connectionOptions
    assert db.statementTimeoutMs > 0
    assert "timezone=" in db.connectionOptions, "the session time zone was lost on the way"


def test_an_unreachable_proxy_keeps_its_address(monkeypatch):
    """S-07: the 502 detail carried the proxyAPI URL to the browser; the log keeps the cause."""
    monkeypatch.setitem(park.source("proxyapi"), "base_url", "http://127.0.0.1:9")
    with pytest.raises(HTTPException) as error:
        asyncio.run(park.fetchStatuses())
    assert error.value.detail == "proxyAPI unreachable"
    assert error.value.__cause__ is not None, "the cause is lost for the log"


def test_a_sign_in_lands_on_supervision_and_a_reload_stays():
    main = (ROOT / "front" / "js" / "main.js").read_text()
    assert "const DEFAULT_VIEW = 'supervision';" in main
    assert "return takeSession(data, true);" in main, "login() does not mark a fresh sign-in"
    assert "const requested = fresh ? '' : window.location.hash.slice(1);" in main
    assert "? takeSession(session) :" in main, "the reload path must not be a fresh sign-in"
