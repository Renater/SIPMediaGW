"""
Supervision: the pool of gateways as the proxyAPI sees it, for the browser.

proxyapi.py reads the proxy (admin token kept server-side, "None" literals
normalised, call duration derived). This route adds what only the browser
needs: the summary counts and, for a call in progress, the Homer link.
"""

import datetime as dt

from fastapi import APIRouter, Depends, HTTPException

from api.periods import aware
from auth import requireUser
from homer import endpointUrl, userPart
from proxyapi import ProxyUnavailable, clean, fetchStatuses

router = APIRouter(dependencies=[Depends(requireUser)])

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
    try:
        pool = await fetchStatuses()
    except ProxyUnavailable as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    now = dt.datetime.now()
    gateways = []
    for g in pool["gateways"]:
        # Live calls have no Call-ID here (the proxyAPI does not carry one),
        # so the trace is searched by calling endpoint: it may return several
        # calls, which the front says explicitly.
        gateways.append({**{k: v for k, v in g.items() if k != "call_started"},
                         "homer_url": liveTraceUrl(g, now)})
    states = [g["state"] for g in gateways]
    return {
        "generated_at": pool["generated_at"],
        "summary": {
            "total": len(gateways),
            "free": states.count("free"),
            "idle": states.count("idle"),
            "ivr": states.count("ivr"),
            "in_call": states.count("call"),
        },
        "gateways": gateways,
    }
