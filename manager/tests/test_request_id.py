"""requestid: one id per request, on the response and on the log lines."""

import logging
import re

from fastapi.testclient import TestClient

import app as application
import requestid


def test_every_response_carries_an_id():
    client = TestClient(application.app)
    header = client.get("/api/me").headers.get("X-Request-ID", "")
    assert re.fullmatch(r"[0-9a-f]{16}", header), f"unexpected id {header!r}"


def test_two_requests_get_two_ids():
    client = TestClient(application.app)
    first = client.get("/api/me").headers["X-Request-ID"]
    second = client.get("/api/me").headers["X-Request-ID"]
    assert first != second


def test_an_upstream_id_is_kept():
    """A reverse proxy's id survives end to end, so its access log matches ours."""
    client = TestClient(application.app)
    response = client.get("/api/me", headers={"X-Request-ID": "nginx-7f3a2c-0042"})
    assert response.headers["X-Request-ID"] == "nginx-7f3a2c-0042"


def test_a_malformed_upstream_id_is_replaced():
    """Anything that could break a log line or a grep is not echoed back."""
    client = TestClient(application.app)
    for bad in ("<script>", "x", "a" * 65, "with space"):
        header = client.get("/api/me", headers={"X-Request-ID": bad}).headers["X-Request-ID"]
        assert header != bad and re.fullmatch(r"[0-9a-f]{16}", header)


def test_log_records_carry_the_id_of_their_request(monkeypatch):
    """
    The point of the exercise: a line logged by a handler names the request.
    Captured on a handler carrying the filter, as the root handler does.
    """
    seen = []

    class Capture(logging.Handler):
        def emit(self, record):
            seen.append(getattr(record, "request_id", None))

    def noDatabase(*args):
        raise RuntimeError("no database in this test")

    # The health probe warns when its query fails; that warning is the line
    # whose id is checked, so the database is made to fail rather than found.
    monkeypatch.setattr(application, "fetch", noDatabase)
    capture = Capture()
    requestid.install(capture)
    logging.getLogger().addHandler(capture)
    try:
        client = TestClient(application.app)
        assert client.get("/health", headers={"X-Request-ID": "probe-test-0001"}).status_code == 503
    finally:
        logging.getLogger().removeHandler(capture)
    assert "probe-test-0001" in seen, f"no record carried the request id: {seen}"


def test_outside_a_request_the_id_is_a_dash():
    """The sampler and startup log too; their lines must still format."""
    assert requestid.requestId.get() == "-"
