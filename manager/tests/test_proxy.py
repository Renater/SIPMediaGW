"""
P12b — the Manager behind a reverse proxy on another machine.

S-08: X-Forwarded-For is believed only when the request comes from a proxy
      declared in FORWARDED_ALLOW_IPS. The port stays open on the LAN for the
      gateways' pushes, and any host there could otherwise forge the header
      and walk around the sign-in throttle.
The "Control" link points at the proxyAPI's public address, not the
internal one the back reads from.
Every path the front calls stays published by the Traefik rule in deploy/.
"""

import re
from pathlib import Path

from fastapi.testclient import TestClient

import app as application
import auth
import sources

ROOT = Path(__file__).resolve().parent.parent


class _Req:
    def __init__(self, host, forwarded=None):
        self.client = type("C", (), {"host": host})()
        self.headers = {"X-Forwarded-For": forwarded} if forwarded else {}


def behind(monkeypatch, spec):
    monkeypatch.setattr(auth, "trustProxy", True)
    monkeypatch.setattr(auth, "trustedProxies", auth.parseProxies(spec))


def test_the_header_is_believed_from_the_declared_proxy_only(monkeypatch):
    behind(monkeypatch, "192.0.2.17")
    assert auth.clientIp(_Req("192.0.2.17", "192.168.1.20")) == "192.168.1.20"
    assert auth.clientIp(_Req("192.0.2.50", "192.168.1.20")) == "192.0.2.50", \
        "a host on the LAN chose its own address"


def test_a_lan_host_cannot_forge_its_way_around_the_throttle(monkeypatch):
    behind(monkeypatch, "192.0.2.17")
    monkeypatch.setattr(auth, "_failures", {})
    for n in range(auth.maxFailures):
        auth.recordLoginFailure(_Req("192.0.2.50", f"10.9.9.{n}"))
    assert auth.loginThrottled(_Req("192.0.2.50", "10.9.9.99")), "a forged header escaped the throttle"


def test_networks_and_wildcard(monkeypatch):
    behind(monkeypatch, "10.0.0.0/8, 192.0.2.17")
    assert auth.clientIp(_Req("10.1.2.3", "192.168.1.20")) == "192.168.1.20"
    behind(monkeypatch, "*")
    assert auth.clientIp(_Req("203.0.113.9", "192.168.1.20")) == "192.168.1.20"


def test_a_bad_entry_is_skipped_not_fatal(monkeypatch):
    behind(monkeypatch, "not-an-address, 192.0.2.17")
    assert auth.clientIp(_Req("192.0.2.17", "192.168.1.20")) == "192.168.1.20"


def test_without_trust_proxy_nothing_changes(monkeypatch):
    monkeypatch.setattr(auth, "trustProxy", False)
    monkeypatch.setattr(auth, "trustedProxies", auth.parseProxies("*"))
    assert auth.clientIp(_Req("192.0.2.17", "192.168.1.20")) == "192.0.2.17"


def test_the_control_link_uses_the_public_address(monkeypatch):
    monkeypatch.setitem(sources.SOURCES["proxyapi"], "base_url", "http://192.0.2.10:80")
    monkeypatch.setitem(sources.SOURCES["proxyapi"], "public_url", "https://visio.sample.org")
    body = TestClient(application.app).get("/api/me").json()
    assert body["interact_url"] == "https://visio.sample.org/interact"


def test_the_public_address_defaults_to_the_internal_one(monkeypatch):
    """Without PROXYAPI_PUBLIC_URL, the browser opens the address the back reads from."""
    import importlib
    monkeypatch.delenv("PROXYAPI_PUBLIC_URL", raising=False)
    monkeypatch.setenv("PROXYAPI_URL", "http://10.0.0.5:80/")
    try:
        importlib.reload(sources)
        proxy = sources.SOURCES["proxyapi"]
        assert proxy["public_url"] == proxy["base_url"] == "http://10.0.0.5:80"
    finally:
        monkeypatch.undo()
        importlib.reload(sources)


def frontPaths():
    """Every absolute path the front asks the server for."""
    calls = re.compile(r"""\b(?:fetch|get|post|put|del|html)\(\s*[`'"](/[^`'"$?]*)""")
    paths = set()
    for script in (ROOT / "front" / "js").rglob("*.js"):
        paths.update(calls.findall(script.read_text()))
    return paths


def managerExclusions(text):
    rule = next(line for line in text.splitlines() if "rule:" in line and "Host(`manager." in line)
    return re.findall(r"!Path(?:Prefix)?\(`([^`]+)`\)", rule)


def test_the_proxy_publishes_everything_the_front_calls():
    """
    The first cut of the Traefik rule hid /health, which the page polls every
    30 s: the banner said the Manager was unreachable while it was not.
    """
    paths = frontPaths()
    assert "/health" in paths and "/auth/login" in paths, "the path scan found nothing"
    for rule in (ROOT / "deploy" / "traefik").glob("*.yml"):
        hidden = managerExclusions(rule.read_text())
        assert "/ingest" in hidden, f"{rule.name}: /ingest is published"
        clash = sorted(p for p in paths if any(p == h or p.startswith(h.rstrip("/") + "/") for h in hidden))
        assert not clash, f"{rule.name} hides paths the front calls: {clash}"


def test_without_configuration_the_page_names_the_product():
    """No MANAGER_BRAND_*: the product's name, no image (.env.example names the shipped ones)."""
    body = TestClient(application.app).get("/api/me").json()
    assert body["brand"] == {"name": "SIP Media Gateway Manager", "tagline": "", "logo": "", "favicon": ""}


def test_a_logo_alone_also_stands_for_the_tab(monkeypatch):
    monkeypatch.setenv("MANAGER_BRAND_LOGO", "logo.svg")
    monkeypatch.delenv("MANAGER_BRAND_FAVICON", raising=False)
    assert application.brandFile("MANAGER_BRAND_LOGO") == "logo.svg"
    assert application.brandFile("MANAGER_BRAND_FAVICON") == ""
    monkeypatch.setenv("MANAGER_BRAND_FAVICON", "../.env")
    assert application.brandFile("MANAGER_BRAND_FAVICON") == "", "a path is refused"


def test_only_the_configured_logo_is_served(tmp_path, monkeypatch):
    (tmp_path / "logo.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
    (tmp_path / "secret.txt").write_text("not served")
    monkeypatch.setattr(application, "BRAND_DIR", str(tmp_path))
    monkeypatch.setattr(application, "brandLogo", "logo.svg")
    monkeypatch.setattr(application, "brandFavicon", "logo.svg")
    client = TestClient(application.app)
    served = client.get("/brand/logo.svg")
    assert served.status_code == 200 and served.headers["content-type"].startswith("image/svg+xml")
    assert client.get("/brand/secret.txt").status_code == 404
    assert client.get("/brand/..%2F.env").status_code == 404
