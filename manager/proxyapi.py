"""
The proxyAPI as the Manager reads it: the pool of gateways and the state of
each one, from /admin/statuses with the admin token.

Read by the /api/gateways route (api/park.py) and by the pool sampler
(sampler.py), which is why this lives here and not in a route module: a
background task does not import routes.

The proxy's mapping format leaks the literal string "None" for room /
browsing / peer_uri / peer_name / call_started; it is normalised here once.
"""

import datetime as dt

import httpx

from sources import source


class ProxyUnavailable(Exception):
    """The proxyAPI did not answer as expected; the message is safe to show."""


_noneLiterals = (None, "", "None")


def clean(value):
    return None if value in _noneLiterals else value


def callSeconds(callStarted, now):
    """Seconds elapsed since call establishment, or None.

    call_started is written by proxyAPI as a naive local ISO timestamp
    (datetime.now().isoformat()); compare against naive local now and
    refuse implausible values rather than display them.
    """
    raw = clean(callStarted)
    if not raw:
        return None
    try:
        started = dt.datetime.fromisoformat(raw)
    except ValueError:
        return None
    if started.tzinfo is not None:
        started = started.astimezone().replace(tzinfo=None)
    seconds = int((now - started).total_seconds())
    return seconds if seconds >= 0 else None


async def fetchStatuses():
    """
    Read the pool from the proxyAPI: {"generated_at", "gateways": [...]}, one
    entry per gateway with its state and what it is doing.
    """
    src = source("proxyapi")
    url = f"{src['base_url']}/admin/statuses"
    headers = {"Authorization": f"Bearer {src['token']}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        # The cause names the proxyAPI's internal address: it stays on the
        # server (the sampler and the route log it), the browser gets the fact.
        raise ProxyUnavailable("proxyAPI unreachable") from exc

    if response.status_code == 401:
        # Configuration error on the Manager side, not a user auth issue:
        # the route must not answer 401 or the front would show the login form.
        raise ProxyUnavailable("proxyAPI rejected the admin token (check PROXYAPI_ADMIN_TOKEN)")
    if response.status_code != 200:
        raise ProxyUnavailable(f"proxyAPI returned {response.status_code}")

    try:
        raw = response.json()
    except ValueError:
        raise ProxyUnavailable("proxyAPI returned a non-JSON body")

    now = dt.datetime.now()
    gateways = []
    for gwId in sorted(raw):
        g = raw[gwId] or {}
        gateways.append({
            # Derived by the proxy since upstream #99: it holds the values
            # and knows what they mean, so nothing here has to guess.
            "state": clean(g.get("state")) or "other",
            "gw_id": gwId,
            "ip": clean(g.get("gateway")),
            "type": clean(g.get("type")),
            "status": clean(g.get("status")),
            "room": clean(g.get("room")),
            "browsing": clean(g.get("browsing")),
            "peer_uri": clean(g.get("peer_uri")),
            "peer_name": clean(g.get("peer_name")),
            "call_started": clean(g.get("call_started")),
            "call_seconds": callSeconds(g.get("call_started"), now),
            "transcript_progress": clean(g.get("transcript_progress")),
            "pairing_code": clean(g.get("pairing_code")),
        })
    return {"generated_at": now.isoformat(timespec="seconds"), "gateways": gateways}
