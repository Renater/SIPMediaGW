"""
Writes come from the console's own pages, or from no browser at all.

The session cookie is SameSite=Lax, which stops another *site* from posting
with it — not another *origin* of the same site. The console shares its site
with interact and Homer (same host on the lab, subdomains of one domain in
production): a script running on one of those pages could post to
/api/org-units/recompute, or create an account, with the administrator's
cookie. So every write is checked here, before any route:

  - Sec-Fetch-Site, sent by every current browser, must say same-origin (or
    none: typed by the user);
  - Origin, when present, must name the host the request was sent to.

A request carrying neither comes from no browser (curl, the tests, a
script): no cookie was lent by anyone, there is nothing to forge. /ingest is
machine-to-machine with its own token, never a cookie, and is left alone.
"""

from urllib.parse import urlsplit

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
EXEMPT_PREFIXES = ("/ingest/",)


def refusal(method: str, path: str, headers, trustForwardedHost: bool = False):
    """
    Why this request must be refused, or None. `headers` is any mapping with
    lower-case keys (Starlette's Headers is case-insensitive).
    """
    if method.upper() in SAFE_METHODS or path.startswith(EXEMPT_PREFIXES):
        return None
    site = (headers.get("sec-fetch-site") or "").lower()
    if site and site not in ("same-origin", "none"):
        return f"Sec-Fetch-Site is {site}"
    origin = headers.get("origin")
    if origin is None:
        return None
    if origin == "null":
        return "Origin is null"
    sender = urlsplit(origin).netloc.lower()
    hosts = {(headers.get("host") or "").lower()}
    if trustForwardedHost and headers.get("x-forwarded-host"):
        hosts.add(headers.get("x-forwarded-host").split(",")[0].strip().lower())
    if sender and sender in hosts:
        return None
    return f"Origin {origin} is not this host"
