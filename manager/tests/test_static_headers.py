"""Static assets revalidate (no-cache + ETag); the entry page is never cached."""

from fastapi.testclient import TestClient

import app as application


def test_static_assets_revalidate_rather_than_refetch():
    client = TestClient(application.app)
    response = client.get("/static/js/main.js")
    assert response.status_code == 200
    assert response.headers.get("Cache-Control") == "no-cache"
    assert response.headers.get("ETag"), "no ETag: no-cache would refetch every time"


def test_a_matching_etag_answers_304():
    client = TestClient(application.app)
    etag = client.get("/static/js/main.js").headers["ETag"]
    assert client.get("/static/js/main.js", headers={"If-None-Match": etag}).status_code == 304


def test_entry_page_is_not_cached():
    client = TestClient(application.app)
    assert client.get("/").headers.get("Cache-Control") == "no-store"
