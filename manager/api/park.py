"""
Real-time park view: relays proxyAPI /admin/statuses.

The relay does three things /admin/statuses does not:
- injects the admin token server-side (the browser never holds it);
- normalises literal "None" strings that the proxy mapping format leaks
  for room / browsing / peer_uri / peer_name / call_started;
- derives call duration and park summary counts, so the front stays dumb.
"""

import datetime as dt
import logging

import httpx
from fastapi import APIRouter, Depends, HTTPException

from api.periods import aware
from auth import requireUser
from homer import endpointUrl, userPart
from sources import source

log = logging.getLogger("manager.park")

router = APIRouter(dependencies=[Depends(requireUser)])

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
    Read the pool from the proxyAPI and derive each gateway's state.
    Shared by the /api/gateways route and the pool sampler.
    """
    src = source("proxyapi")
    url = f"{src['base_url']}/admin/statuses"
    headers = {"Authorization": f"Bearer {src['token']}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(url, headers=headers)
    except httpx.HTTPError as exc:
        # The cause names the proxyAPI's internal address: it stays on the
        # server (the sampler logs it), the browser gets the fact.
        raise HTTPException(status_code=502, detail="proxyAPI unreachable") from exc

    if response.status_code == 401:
        # Configuration error on the Manager side, not a user auth issue:
        # do not surface it as 401 or the front would show the login form.
        raise HTTPException(status_code=502,
                            detail="proxyAPI rejected the admin token "
                                   "(check PROXYAPI_ADMIN_TOKEN)")
    if response.status_code != 200:
        raise HTTPException(status_code=502,
                            detail=f"proxyAPI returned {response.status_code}")

    try:
        raw = response.json()
    except ValueError:
        raise HTTPException(status_code=502,
                            detail="proxyAPI returned a non-JSON body")

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
            "call_seconds": callSeconds(g.get("call_started"), now),
            "transcript_progress": clean(g.get("transcript_progress")),
            "pairing_code": clean(g.get("pairing_code")),
            # Live calls have no Call-ID here (the proxyAPI does not carry
            # one), so the trace is searched by calling endpoint: it may
            # return several calls, which the front says explicitly.
            "homer_url": liveTraceUrl(g, now),
        })

    states = [g["state"] for g in gateways]
    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "summary": {
            "total": len(gateways),
            "free": states.count("free"),
            "idle": states.count("idle"),
            "ivr": states.count("ivr"),
            "in_call": states.count("call"),
        },
        "gateways": gateways,
    }


def liveTraceUrl(gateway, now):
    """Homer search for a call in progress, or None when there is nothing to open."""
    fromUser = userPart(clean(gateway.get("peer_uri")))
    if not fromUser:
        return None
    started = clean(gateway.get("call_started"))
    since = None
    if started:
        try:
            # The proxy writes a local time with no zone: made aware here, or
            # the retention check in homer.py compares it with an aware one.
            since = aware(dt.datetime.fromisoformat(started.replace("Z", "+00:00")))
        except ValueError:
            since = None
    # No start time: fall back to a day, wide enough to be sure the call is in.
    if since is None:
        since = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=1)
    return endpointUrl(fromUser, since, dt.datetime.now(dt.timezone.utc))


@router.get("/gateways")
async def gateways():
    return await fetchStatuses()
