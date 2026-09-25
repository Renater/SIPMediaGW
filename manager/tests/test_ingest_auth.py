"""authorizeIngest: the shared token, and the closed-by-default rule."""
from unittest.mock import Mock

import pytest

import ingest.router as ingest


def request(header):
    return Mock(headers={"Authorization": header} if header is not None else {})


@pytest.fixture
def token(monkeypatch):
    monkeypatch.setattr(ingest, "ingestToken", "s3cret")


def test_valid_bearer(token):
    assert ingest.authorizeIngest(request("Bearer s3cret")) is True


@pytest.mark.parametrize("header", ["Bearer wrong", "Basic czNjcmV0", "s3cret", "", None])
def test_rejected(token, header):
    assert ingest.authorizeIngest(request(header)) is False


def test_unset_token_closes_the_route(monkeypatch):
    monkeypatch.setattr(ingest, "ingestToken", "")
    assert ingest.authorizeIngest(request("Bearer ")) is False


def test_oversized_body_is_refused(monkeypatch):
    """
    A declared length over the cap is refused before the body is read; an
    undeclared one is refused as soon as the cap is passed. Both answer 413,
    never a 500 from a JSON parser fed a gigabyte.
    """
    from fastapi.testclient import TestClient
    import ingest.router as ingest
    import app as application

    monkeypatch.setattr(ingest, "ingestToken", "secret")
    monkeypatch.setattr(ingest, "MAX_BODY_BYTES", 100)
    client = TestClient(application.app)
    headers = {"Authorization": "Bearer secret", "Content-Type": "application/json"}

    declared = client.post("/ingest/calls", headers={**headers, "Content-Length": "101"},
                           content=b"x" * 101)
    assert declared.status_code == 413

    small = client.post("/ingest/calls", headers=headers, content=b"{}")
    assert small.status_code != 413, "a small body must not trip the cap"


def test_the_cap_covers_a_long_call_with_samples(monkeypatch):
    """
    Samples add about 60 bytes a second: the former 1 MB cap stopped at about
    4 h 30, less than a room left connected all day. The default is 8 MB.
    """
    import os
    import ingest.router as ingest
    if not os.getenv("INGEST_MAX_BODY_BYTES"):
        assert ingest.MAX_BODY_BYTES == 8 * 1024 * 1024
    assert 'str(8 * 1024 * 1024)' in open(ingest.__file__).read()


def test_a_refused_size_leaves_a_trace(monkeypatch, caplog):
    """The gateway does not keep a refused push: the log line is the only trace."""
    import logging
    from fastapi.testclient import TestClient
    import ingest.router as ingest
    import app as application

    monkeypatch.setattr(ingest, "ingestToken", "secret")
    monkeypatch.setattr(ingest, "MAX_BODY_BYTES", 100)
    client = TestClient(application.app)
    with caplog.at_level(logging.WARNING, logger="manager.ingest"):
        response = client.post("/ingest/calls", content=b"x" * 101,
                               headers={"Authorization": "Bearer secret",
                                        "Content-Type": "application/json"})
    assert response.status_code == 413
    assert any("101 bytes" in r.getMessage() and "INGEST_MAX_BODY_BYTES" in r.getMessage()
               for r in caplog.records)


def test_a_push_without_call_id_is_refused(monkeypatch):
    """
    A container stopping without a call pushes an empty callId: refused with a
    400 before the database is touched (the route has none here). A Call-ID
    without a start is a different case, kept: see test_ingest_db.
    """
    import json
    from pathlib import Path
    from fastapi.testclient import TestClient
    import ingest.router as ingest
    import app as application

    monkeypatch.setattr(ingest, "ingestToken", "secret")
    empty = json.loads((Path(__file__).parent / "fixtures" / "payload_empty.json").read_text())
    response = TestClient(application.app).post(
        "/ingest/calls", json=empty, headers={"Authorization": "Bearer secret"})
    assert response.status_code == 400
    assert "callId" in response.json()["detail"]
