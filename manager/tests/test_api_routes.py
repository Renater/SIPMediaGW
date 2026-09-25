"""
Call every API route, without a database.

The four failures of one afternoon were all route failures: a variable used
before it was defined, a period parameter dropped from a query, a result renamed
in one place and not the other, a column that did not exist. Three of the four
show up the moment a route is called at all — which is exactly what these tests
do, and what nothing did before.

`fetch` is replaced by a recorder, so no PostgreSQL is needed and the whole file
runs in well under a second. What that cannot check is whether the SQL matches
the schema; `test_api_sql.py` covers that side statically.

The recorder returns an empty result by default. That is deliberate: an endpoint
must survive a month with no data — the first month of any deployment — and a
handler that assumes at least one row is a bug waiting for a quiet August.
"""

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def routeModules():
    """The api modules that own routes and bind fetch/execute by name."""
    import importlib
    modules = [importlib.import_module(f"api.{name}") for name in ("usage", "quality", "pool", "calls", "org_units", "audit")]
    # The account SQL lives in users.py at the root, read by api/users.py.
    return modules + [importlib.import_module("users")]


class Recorder:
    """Stands in for db.fetch, keeping what was asked and answering with rows."""

    def __init__(self):
        self.calls = []
        self.rows = []
        # Answers for the next calls, in order, before falling back to rows:
        # a route that reads twice then writes needs three different answers.
        self.queue = []

    def __call__(self, query, params=()):
        # users.py composes its queries with psycopg.sql: rendered, they are
        # checked like the others.
        if not isinstance(query, str):
            query = query.as_string(None)
        flat = " ".join(query.split())
        # The one thing a stub can check about a query: that the handler
        # bound as many values as the text expects. Off by one here is a
        # psycopg error in production and was invisible to this fixture.
        expected, given = flat.count("%s"), len(params)
        assert expected == given, f"{expected} placeholders, {given} parameters: {flat[:120]}"
        self.calls.append((flat, tuple(params)))
        # Copies of the rows, not the rows: a handler that pops a key from
        # what it received (the page total, say) emptied SAMPLE_ROW for every
        # route called after it in the sweep.
        if self.queue:
            return [dict(row) for row in self.queue.pop(0)]
        return [dict(row) for row in self.rows]

    def lastParams(self):
        return self.calls[-1][1] if self.calls else ()

    def queriesMentioning(self, text):
        return [q for q, _ in self.calls if text in q]


SAMPLE_ROW = {
        "month": "2026-08-01", "day": "2026-08-01", "hour": 10, "day_type": "default",
        "calls": 12, "hours": 3.5, "sessions": 4, "pct": 12.5, "gateway_hours": 1.5,
        "org_unit": "SALES", "platform": "visio", "outcome": "completed",
        "close_reason": "Connection reset by peer [104]", "is_failure": False,
        "provisioned_avg": 4.2, "provisioned_peak": 9, "busy_avg": 2.1, "busy_peak": 7,
        "busy_p95": 6.0, "spare_avg": 2.1, "spare_peak": 5, "running_avg": 3.0,
        "free_avg": 1.2, "utilisation_pct": 50.0, "samples": 44640,
        "provisioned_hours": 263.2, "call_hours": 120.0, "idle_paid_hours": 143.2,
        "hourly_cost": 0.44, "cost": 115.81, "idle_cost": 63.0, "coverage_pct": 98.0,
        "median": 3.0, "p90": 5.0, "p95": 6.0, "p99": 8.0, "peak": 9,
        "avg_concurrent": 2.4, "sampled_peak": 8, "idle_hours": 10.0, "ivr_hours": 1.0,
        "no_spare_samples": 3, "no_spare_pct": 1.2, "no_spare_minutes": 3.0,
        "cold_start_minutes": 1.0, "avg_occupancy_s": 314, "peak_concurrent": 9,
        "first_seen": "2026-08-01", "last_seen": "2026-08-31", "avg_seconds": 1800,
        "valid_from": "2026-08-01", "updated_at": "2026-08-01T00:00:00+00:00",
        "key": "vm_hourly_cost", "value": "0.44",
        "rows_seen": 194, "rows_moved": 0, "ran_by": "gw_manager", "note": None,
        "days": 22, "ran_at": "2026-08-01T00:00:00+00:00", "id": 1,
    # COUNT(*) OVER () rides along with each row of the call log: the page and
    # its total come back in one query.
    "total": 1, "call_id": "abc", "source_uri": "sip:12345@rooms.sample.org",
    "peer_display_name": "Room 12", "gw_alias": "gw0", "source_name": "Room",
    "source_number": "12345", "call_start": "2026-08-01T10:00:00+00:00",
    "call_end": "2026-08-01T11:00:00+00:00", "duration_s": 3600,
    "occupancy_s": 3640, "media": "audio", "stream_index": 0,
    "direction": "rx", "packets": 100, "errors": 0, "packet_reports": 3,
    "lost_packets": 1, "main_app": "baresip", "call_url": None,
    "destination_uri": "sip:123@visio.sample.org", "last_event_type": "CALL_CLOSED",
    # Fields a handler writes back into the row it returns — a Homer link, a
    # running total. Present here so the sweep exercises the assignment rather
    # than tripping over a missing key on the way to it.
    "running_hours": 300.0, "cumulative_calls": 12, "cumulative_hours": 3.5,
    "homer_url": None, "homer_link_kind": None, "label": "2026-08",
    "since": "2026-08-01T00:00:00+00:00", "until": "2026-09-01T00:00:00+00:00",
    "peak_running": 9, "peak_in_call": 7, "first_sample": "2026-08-01T00:00:00+00:00",
    # Accounts (users.py): what api/users.py reads back, and the audit line.
    "username": "test", "role": "operator", "source": "local", "enabled": True, "must_change_password": False,
    "session_epoch": 0, "password_hash": None, "password_changed_at": None, "external_id": None,
    "created_at": "2026-08-01T00:00:00+00:00", "created_by": "test",
    "first_name": "Test", "last_name": "User", "last_login_at": None,
    "at": "2026-08-01T00:00:00+00:00", "actor": "test", "action": "create",
    "target": "test", "detail": {}, "n": 0,
    "last_sample": "2026-08-31T23:59:00+00:00", "not_completed": 2,
    "received_at": "2026-08-01T11:00:01+00:00", "gw_host": "gw0", "raw": {},
    # Call log since P16: the endpoint read from its User-Agent, and the
    # frames per second the drawer draws, both written back by the handler.
    "peer_user_agent": "TANDBERG/529 (ce11.40.1.1) Cisco-RoomKitMini",
    "terminal": "Cisco-RoomKitMini", "frame_rates": [],
    # Entities (P22): the probe reads whether the rule's entity is active.
    "unit_active": True,
    }


# What an empty database gives an aggregate: one row, every count at zero. Built
# from SAMPLE_ROW so the two cannot drift apart — a field added to one is present
# in the other.
EMPTY_ROW = {
    key: (None if key in ("cost", "idle_cost", "hourly_cost", "note", "room",
                          "close_reason", "org_unit", "platform")
          else 0 if isinstance(value, (int, float)) else value)
    for key, value in SAMPLE_ROW.items()
}


@pytest.fixture()
def client(monkeypatch):
    """
    A test client with an authenticated session and no database behind it.

    The route modules do `from db import fetch`, so the name is bound at import
    time in each: patching `db.fetch` would leave those bindings untouched. Patching the
    module attribute is enough, and reloading modules — which an earlier version
    of this fixture did — only made the failure harder to read.
    """
    from fastapi.testclient import TestClient

    import app as application
    import auth

    recorder = Recorder()
    # Every route module binds fetch and execute by name at import; each one is
    # patched, or the sweep would reach the real database through the one that
    # was missed.
    for module in routeModules():
        monkeypatch.setattr(module, "fetch", recorder, raising=False)
        monkeypatch.setattr(module, "execute", recorder, raising=False)
    application.app.dependency_overrides[auth.requireUser] = lambda: "test"
    application.app.dependency_overrides[auth.requireAdmin] = lambda: "test"

    testClient = TestClient(application.app)
    testClient.recorder = recorder
    yield testClient
    application.app.dependency_overrides.clear()


# /api/gateways relays the proxy over HTTP rather than reading the database, and
# /api/me reports whether a session exists, so it answers without one. Sweeping
# them here would test httpx and the session middleware, not the handlers.
NOT_DATABASE_BACKED = {"/api/gateways", "/api/me"}
# /health is meant for the orchestrator, which carries no session.
PUBLIC = {"/health"}


def aggregateRoutes():
    """
    Routes whose handler reads `rows[0]` without checking, and is right to.

    A query that aggregates without grouping returns exactly one row, empty table
    or not, so the handler is entitled to index it. Which routes those are is
    read from the source rather than listed here: a hand-kept list goes stale the
    day a route stops aggregating, and then the test quietly stops covering it.
    """
    source = "\n".join(p.read_text() for p in (Path(__file__).resolve().parent.parent / "api").glob("*.py"))
    routes = set()
    for match in re.finditer(r'@router\.get\("([^"]+)"\)\ndef (\w+)', source):
        body = source[match.end():]
        end = body.find("\n@router")
        body = body[:end if end > 0 else len(body)]
        # `if not rows` is a guard too, and the first version of this check did
        # not see it — it looked for the literal "if rows" and reported a route
        # that raises a clean 404 as one that crashes. A detector that is wrong
        # about the code is worse than no detector: it was about to send someone
        # fixing a bug that did not exist.
        guarded = re.search(r"if\s+not\s+rows\b|if\s+rows\b", body)
        if "rows[0]" in body and not guarded:
            routes.add("/api" + match.group(1))
    return routes


def apiRoutes(application, skip=NOT_DATABASE_BACKED):
    """
    Every GET route under /api that needs no path parameter.

    Read from the OpenAPI schema rather than from `app.routes`: how FastAPI
    stores an included router is an internal detail that changed between
    versions, and walking it found nothing here — the sweep passed while testing
    no route at all, which is worse than failing. The schema is the published
    description of the same thing and does not move.
    """
    paths = application.openapi().get("paths", {})
    routes = {
        path for path, operations in paths.items()
        if path.startswith("/api") and "get" in operations and "{" not in path
    }
    return sorted(routes - skip - PUBLIC)


def test_the_sample_row_carries_every_field_a_handler_reads():
    """
    The fixture has to keep up with the handlers.

    Twice in a row the sweep failed not on a bug but on a key the sample row did
    not carry — `total` from the call log, the running total the monthly series
    writes back. Rather than discover the next one from a stack trace, the fields
    the handlers name are read from the source and compared here.
    """
    source = "\n".join(p.read_text() for p in (Path(__file__).resolve().parent.parent / "api").glob("*.py"))
    read = set()
    for variable in ("row", "result", "r", "call", "entry"):
        read |= set(re.findall(rf'\b{variable}\["(\w+)"\]', source))
        read |= set(re.findall(rf'\b{variable}\.get\("(\w+)"', source))
    missing = sorted(read - set(SAMPLE_ROW))
    assert not missing, (
        "SAMPLE_ROW is missing fields the handlers read: " + ", ".join(missing))


def test_the_sample_row_carries_what_the_account_routes_read():
    """
    The account routes read their rows through public(), with a name the
    check above does not look for. Two keys were missing and the sweep
    raised a KeyError from inside a route instead of naming them.
    """
    source = (Path(__file__).resolve().parent.parent / "api" / "users.py").read_text()
    read = set(re.findall(r'account\["(\w+)"\]', source))
    missing = sorted(read - set(SAMPLE_ROW))
    assert not missing, f"SAMPLE_ROW is missing account fields: {missing}"


def test_the_sweep_actually_sweeps():
    """
    A guard on the guard.

    `apiRoutes` returning an empty list makes every test built on it pass
    without testing anything. That happened twice: once because the routers were
    not where they were looked for, once because the fix looked in a second
    wrong place. The count is asserted on its own so the failure names the cause
    instead of hiding behind a sweep that found nothing to do.
    """
    import app as application

    routes = apiRoutes(application.app)
    assert len(routes) >= 15, (
        f"only {len(routes)} routes discovered — every sweep below is vacuous. "
        f"Found: {routes}")


def test_every_get_route_answers(client):
    """
    The blunt one, and the one that would have caught three of the four failures.

    The row handed back is what an empty database actually returns: an aggregate
    on an empty table gives one row whose counts are zero, not no row at all. A
    handler reading `rows[0]` is right to, and feeding it nothing would fail the
    routes that count things while proving only that the fixture is unrealistic.
    """
    import app as application

    client.recorder.rows = [EMPTY_ROW]
    failures = []
    for path in apiRoutes(application.app):
        response = client.get(path)
        if response.status_code != 200:
            failures.append(f"{path} -> {response.status_code} {response.text[:140]}")
    assert not failures, "\n".join(failures)


def test_list_routes_survive_an_empty_result(client):
    """
    The other half: a query listing rows returns nothing at all when there is
    nothing, and a handler indexing into that list breaks on the first month of
    a deployment.

    Routes whose SQL aggregates without grouping are left out — SQL guarantees
    them a row, and asking them to survive its absence tests a case that cannot
    happen.
    """
    import app as application

    client.recorder.rows = []
    failures = []
    for path in apiRoutes(application.app, skip=NOT_DATABASE_BACKED | aggregateRoutes()):
        response = client.get(path)
        if response.status_code != 200:
            failures.append(f"{path} -> {response.status_code} {response.text[:140]}")
    assert not failures, "\n".join(failures)


def test_every_get_route_answers_with_data(client):
    """
    Same sweep, with a row coming back.

    An empty result hides the handlers that read fields off a row: a renamed
    column, a field the query no longer selects, an index into an empty list.
    The row below carries every field any handler reads, so the shape is wrong
    for most of them and right for none — which is fine, because what is being
    tested is that reading it does not raise.
    """
    import app as application

    client.recorder.rows = [SAMPLE_ROW]
    failures = []
    for path in apiRoutes(application.app):
        response = client.get(path)
        if response.status_code != 200:
            failures.append(f"{path} -> {response.status_code} {response.text[:160]}")
    assert not failures, "\n".join(failures)


@pytest.mark.parametrize("path", [
    "/api/reporting/summary",
    "/api/reporting/org-units",
    "/api/reporting/platforms",
    "/api/reporting/outcomes",
    "/api/reporting/ivr-reasons",
    "/api/reporting/pool-profile",
    "/api/reporting/pool-pressure",
    "/api/reporting/pool-period-hours",
    "/api/reporting/concurrency/hourly",
])
def test_period_reaches_the_query(client, path):
    """
    A period parameter that never reaches the SQL is invisible: the page shows
    figures, they are simply the wrong month. That is how the close-reason table
    came to display the current day while the page said September.
    """
    client.recorder.rows = [EMPTY_ROW]
    client.get(f"{path}?period=2026-08")
    assert client.recorder.calls, f"{path} ran no query"
    params = " ".join(str(p) for call in client.recorder.calls for p in call[1])
    assert "2026-08" in params, f"{path} never passed the period to the database"


def test_unit_filter_reaches_the_query(client):
    """
    Selecting every unit must send no filter at all, so that totals do not move
    as the last box is ticked — and selecting one must send exactly that one.
    """
    client.recorder.rows = [EMPTY_ROW]
    client.recorder.calls.clear()
    client.get("/api/reporting/summary?period=2026-08")
    assert not any("org_unit = ANY" in q for q, _ in client.recorder.calls)

    client.recorder.calls.clear()
    client.get("/api/reporting/summary?period=2026-08&units=SALES,FINANCE")
    filtered = [c for c in client.recorder.calls if "org_unit = ANY" in c[0]]
    assert filtered, "units= did not reach the query"
    assert ["SALES", "FINANCE"] in [p for call in filtered for p in call[1]]


def test_unassigned_is_selectable(client):
    """
    Rows no rule catches are the ones worth looking at, so the bucket holding
    them has to be selectable like any other unit.
    """
    client.recorder.rows = [EMPTY_ROW]
    client.get("/api/reporting/summary?period=2026-08&units=(unassigned)")
    assert any("org_unit IS NULL" in q for q, _ in client.recorder.calls)


def test_unknown_identifiers_answer_404(client):
    """
    Routes taking an identifier are left out of the sweep, since it cannot invent
    one — so they are covered here instead.

    An identifier nobody recognises is a client mistake, not a server fault: the
    answer is 404, never a stack trace. Checking it also keeps the gap visible;
    excluding a route from the sweep is easy to do and easy to forget.
    """
    client.recorder.rows = []
    for path in ("/api/reporting/calls/999999", "/api/reporting/calls/999999/media"):
        response = client.get(path)
        assert response.status_code == 404, (
            f"{path} answered {response.status_code}: an unknown id is a 404")


def test_routes_are_guarded(monkeypatch):
    """
    Every /api route sits behind the session. Without the override above, the
    answer is 401 — the check that the guard is wired, not bypassed by a route
    declared outside the router.
    """
    from fastapi.testclient import TestClient
    recorder = Recorder()
    recorder.rows = [EMPTY_ROW]
    for module in routeModules():
        monkeypatch.setattr(module, "fetch", recorder, raising=False)
        monkeypatch.setattr(module, "execute", recorder, raising=False)
    import app as application

    client = TestClient(application.app)
    unguarded = []
    for path in apiRoutes(application.app):
        if client.get(path).status_code != 401:
            unguarded.append(path)
    assert not unguarded, f"routes answering without a session: {unguarded}"


def test_search_wildcards_match_themselves(client):
    """
    `%` and `_` are ILIKE wildcards. Typed by an operator looking for "50%",
    they matched every call; escaped, they match the text as typed.
    """
    client.get("/api/reporting/calls?q=50%25_x")
    params = client.recorder.lastParams()
    assert "%50\\%\\_x%" in params, f"wildcards not escaped: {params}"


def test_call_search_mixes_zoned_and_default_bounds(client):
    """A zoned start with no end used to be a 500 (aware vs naive comparison)."""
    assert client.get("/api/reporting/calls?start=2026-09-01T00:00:00Z").status_code == 200
    assert client.get("/api/reporting/calls?end=2099-01-01T00:00:00%2B02:00").status_code == 200


def test_the_vm_cost_is_decommissioned(client):
    """
    The cost in euros left out the fixed infrastructure and the services
    around it, and was read as the cost of the service: its routes are gone,
    and VM-hours replace it. A 404, not a 500 from a half-removed module.
    """
    for method, path in (("get", "/api/rates"), ("put", "/api/rates/2026-09-01"),
                         ("delete", "/api/rates/2026-09-01"), ("get", "/api/reporting/pool-cost")):
        response = getattr(client, method)(path)
        assert response.status_code in (404, 405), f"{method.upper()} {path} answered {response.status_code}"


def test_period_hours_reach_their_query(client):
    """Hours of the period, conference hours, and the share sampled."""
    client.recorder.rows = [SAMPLE_ROW]
    body = client.get("/api/reporting/pool-period-hours?period=2026-08").json()
    query, params = client.recorder.calls[-1]
    assert "FROM pool_samples" in query and "in_call * interval_s" in query
    assert str(params[1]) == "2026-08-01" and str(params[3]) == "2026-09-01"
    assert body["label"] == "2026-08" and "provisioned_hours" in body and "call_hours" in body


def test_write_routes_are_guarded(monkeypatch):
    """A write without a session is refused like a read: 401, never 405 or 500."""
    from fastapi.testclient import TestClient
    import app as application

    recorder = Recorder()
    recorder.rows = [SAMPLE_ROW]
    # monkeypatch, not assignment: a bare assignment left the stub in every
    # route module for the rest of the session.
    for module in routeModules():
        monkeypatch.setattr(module, "fetch", recorder, raising=False)
        monkeypatch.setattr(module, "execute", recorder, raising=False)
    anonymous = TestClient(application.app)
    assert anonymous.post("/api/users", json={"username": "x@y.fr"}).status_code == 401
    assert anonymous.delete("/api/users/x@y.fr").status_code == 401


def test_bad_period_is_refused(client):
    """
    A period that is not a period is refused, and refused as a client error.

    The first version of this accepted 200, 400 or 422 — three answers out of
    three, which is not an assertion. `resolvePeriod` already decides: anything
    that is neither a named period nor YYYY-MM nor YYYY raises 400. The test
    says so, and now fails if that changes.
    """
    for period in ("not-a-month", "2026-13", "2026-1", "last_century", "../etc"):
        response = client.get(f"/api/reporting/summary?period={period}")
        assert response.status_code == 400, (
            f"period={period} answered {response.status_code}, expected 400")


def test_day_type_is_validated(client):
    """
    The hourly route interpolates nothing, but the day type reaches a WHERE
    clause as a parameter and the accepted values are a closed set.
    """
    assert client.get("/api/reporting/concurrency/hourly?dayType=default").status_code == 200
    for day in ("monday", "friday", "saturday", "sunday"):
        assert client.get(f"/api/reporting/concurrency/hourly?dayType={day}").status_code == 200, day
    for bad in ("lundi", "Monday", "weekend", ""):
        assert client.get(f"/api/reporting/concurrency/hourly?dayType={bad}").status_code == 400, bad
