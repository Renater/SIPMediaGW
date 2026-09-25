"""
Deep links from a call to its SIP trace in Homer.

The URL format below was validated empirically against our instance
(Homer 7, homer-app 1.5.20), including by negative control: an impossible
value must return zero results. The /search/result route accepts the query as
a JSON blob in the query string and the UI consumes it, including after a
redirect through the login page.

The URL format is NOT the API format (POST /api/v3/search/call/data expects a
different structure); the API is not used here.

Filter names matter, and getting one wrong tells you nothing:
    callid                -> short form, value is an ARRAY
    data_header.<field>   -> generic form, value is a SCALAR
    user_from / from_user -> SILENTLY IGNORED
An unrecognised name does not raise: the page renders without the filter, so
with every call in the window. Any filter added here must be validated by a
negative control; a test with an existing value proves nothing.

Everything version-specific lives in _urlV7 / _urlV11, so migrating to
Homer 11 means changing one function body.
"""

import datetime as dt
import json
import logging
import os
from urllib.parse import quote

log = logging.getLogger("manager.homer")

baseUrl = os.getenv("HOMER_BASE", "").rstrip("/")
flavor = os.getenv("HOMER_FLAVOR", "v7")
profile = os.getenv("HOMER_PROFILE", "1_call")
# Days of SIP capture Homer still holds. Past that the link would open an empty
# page, so none is offered. 0 disables the check.
retentionDays = int(os.getenv("HOMER_RETENTION_DAYS", "0"))

# Padding around the call, so the INVITE and the BYE fall inside the window.
# data_header.* filters run as a JSONB lookup whose index is not guaranteed
# (heplify-server owns the schema), so the window stays deliberately tight.
PRE_SECONDS = 60
POST_SECONDS = 60
# Fallback length when the call has no recorded end.
FALLBACK_MS = 300_000
LIMIT = 200

# Only the characters that would break the URL are escaped. Braces, quotes,
# "@" and ":" stay raw: that is the form that was validated. "#" matters most,
# since a browser would truncate the link there.
_ESCAPES = (("%", "%25"), ("#", "%23"), ("&", "%26"), (" ", "%20"), ("+", "%2B"))


def _urlV7(filters, startMs, endMs):
    query = {
        "param": {"search": {profile: filters}, "limit": LIMIT},
        "timestamp": {"from": startMs - PRE_SECONDS * 1000,
                      "to": endMs + POST_SECONDS * 1000},
    }
    blob = json.dumps(query, separators=(",", ":"))
    for char, escaped in _ESCAPES:
        blob = blob.replace(char, escaped)
    # The trailing "=" is emitted explicitly: Chrome adds it on its own, other
    # browsers may not, and we would rather not depend on that.
    return f"{baseUrl}/search/result?{blob}="


def _urlV11(filters, startMs, endMs):
    callIds = filters.get("callid") or []
    if not callIds:
        return None                          # the v11 shape only covers Call-ID
    return (f"{baseUrl}/?call_id={quote(callIds[0])}"
            f"&from={startMs - PRE_SECONDS * 1000}"
            f"&to={endMs + POST_SECONDS * 1000}#dashboard")


_BUILDERS = {"v7": _urlV7, "v11": _urlV11}


def _aware(value):
    """Naive datetimes are local times; attach the zone without moving them."""
    if isinstance(value, dt.datetime) and value.tzinfo is None:
        return value.astimezone()
    return value


def _epochMs(value):
    return int(value.timestamp() * 1000) if isinstance(value, dt.datetime) else None


def searchUrl(filters, callStart, callEnd=None):
    """
    Link to a Homer search, or None when there is nothing to link to.

    `filters` is already in Homer's shape, for example {"callid": ["abc"]} or
    {"data_header.to_user": "3.wqpmzrtkcx"}. Filters combine with an implicit
    AND (param.orlogic is false by default).
    """
    if not baseUrl or not filters:
        return None
    builder = _BUILDERS.get(flavor)
    if builder is None:
        log.warning("unknown HOMER_FLAVOR %r, no Homer link", flavor)
        return None

    # Public function: callers pass DB timestamps (aware) but also parsed
    # strings (naive). Normalised here so the retention comparison below
    # cannot raise.
    callStart = _aware(callStart)
    callEnd = _aware(callEnd)
    startMs = _epochMs(callStart)
    if startMs is None:
        return None
    endMs = _epochMs(callEnd) or (startMs + FALLBACK_MS)
    if endMs < startMs:
        endMs = startMs + FALLBACK_MS

    if retentionDays > 0:
        oldest = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=retentionDays)
        if callStart < oldest:
            return None                      # capture already rotated out

    return builder(filters, startMs, endMs)


def traceUrl(callId, callStart, callEnd=None):
    """Exact link: one call, identified by its SIP Call-ID."""
    if not callId:
        return None
    return searchUrl({"callid": [callId]}, callStart, callEnd)


def roomUrl(toUser, callStart, callEnd=None):
    """
    Approximate link: every call to the same room within the window.

    This does not identify a single call — two endpoints joining the same room
    in the window show up together — so the caller must label it differently
    from the exact link.
    """
    if not toUser:
        return None
    return searchUrl({"data_header.to_user": toUser}, callStart, callEnd)


def endpointUrl(fromUser, since, until=None):
    """
    Approximate link: every call placed by one endpoint within the window.

    Used for a call in progress, where the Call-ID is not available from the
    proxyAPI. Validated by negative control on our instance: an impossible
    value returns zero rows, so the filter really filters — unlike the bare
    "from_user" name, which Homer ignores silently.
    """
    if not fromUser:
        return None
    return searchUrl({"data_header.from_user": fromUser}, since, until)


def userPart(uri):
    """User part of a SIP URI: sip:test@host -> test."""
    if not uri:
        return None
    value = uri.split("@", 1)[0].strip()
    if value.lower().startswith("sip:"):
        value = value[4:]
    return value or None


def roomFilterValue(destinationUri, room=None):
    """
    The value Homer indexed as data_header.to_user.

    Taken from the user part of the destination URI rather than rebuilt from
    the room: the URI already carries the platform prefix Homer sees
    ("3.abcdefghij@visio.example.org" -> "3.abcdefghij"), so there is no
    per-platform prefix to guess. Falls back to the bare room when the URI is
    missing, which is a weaker guess.
    """
    if destinationUri:
        user = destinationUri.split("@", 1)[0].strip()
        if user:
            return user
    return room or None


def callLink(call):
    """
    Best available link for one call, with its kind so the front can label it.

    Returns (url, kind) with kind "exact" or "room", or (None, None) when
    neither is usable — the front then shows no button at all.
    """
    url = traceUrl(call.get("call_id"), call.get("call_start"), call.get("call_end"))
    if url:
        return url, "exact"
    toUser = roomFilterValue(call.get("destination_uri"), call.get("room"))
    url = roomUrl(toUser, call.get("call_start"), call.get("call_end"))
    if url:
        return url, "room"
    return None, None
