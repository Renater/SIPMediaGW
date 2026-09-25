"""
One identifier per request, on every log line it produces and in its response.

The id lives in a context variable: set by the middleware before the handler
runs, it follows the request through awaits and into the threads FastAPI uses
for synchronous handlers (contextvars are copied into to_thread calls). The
logging filter reads it back, so no logger has to be told about it.

Outside a request — the sampler, startup, the health probe's own logging — the
value is "-", which keeps the format valid and makes those lines easy to spot.
"""

import contextvars
import logging
import re
import uuid

from starlette.middleware.base import BaseHTTPMiddleware

HEADER = "X-Request-ID"
# What an upstream id may look like to be kept: long enough to be one, short
# enough to be a header, and nothing that would break a log line or a grep.
ACCEPTED = re.compile(r"^[A-Za-z0-9._-]{8,64}$")

requestId: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


def newId() -> str:
    """Sixteen hex characters: unique enough for one console, short enough to read."""
    return uuid.uuid4().hex[:16]


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Sets the id for the request's duration and returns it in the response."""

    async def dispatch(self, request, call_next):
        incoming = request.headers.get(HEADER, "")
        current = incoming if ACCEPTED.match(incoming) else newId()
        token = requestId.set(current)
        try:
            response = await call_next(request)
        finally:
            requestId.reset(token)
        response.headers[HEADER] = current
        return response


class RequestIdFilter(logging.Filter):
    """Adds request_id to every record so the format can print it."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = requestId.get()
        return True


def install(handler: logging.Handler) -> None:
    """Attach the filter once; basicConfig may run more than once under reload."""
    if not any(isinstance(f, RequestIdFilter) for f in handler.filters):
        handler.addFilter(RequestIdFilter())
