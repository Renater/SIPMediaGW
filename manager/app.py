"""
Manager — application entry point.

This module only wires things together: session middleware, routers and the
static front. Business logic lives in api/ (read routes), ingest/ (call
history intake) and auth.py (the single authorisation point).
"""

import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
import os
import secrets

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.concurrency import run_in_threadpool
from starlette.middleware.sessions import SessionMiddleware

import auth
import origin
import requestid
from api.park import router as parkRouter
from api import audit, calls, org_units, pool, quality, usage, users
from db import DatabaseUnavailable, fetch
import sampler
from ingest.router import router as ingestRouter
from sources import source

FRONT_DIR = os.path.join(os.path.dirname(__file__), "front")

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s [%(request_id)s]: %(message)s",
)
# The root handler is the only one using the format above; uvicorn keeps its
# own. Every record reaching it passes through the filter, whichever logger
# produced it.
for _handler in logging.getLogger().handlers:
    requestid.install(_handler)
# httpx announces every request to the proxyAPI at INFO: one per poll per open
# tab, one per sampler tick. The sampler logs the failures itself; the successes
# are noise that buries the lines worth reading.
logging.getLogger("httpx").setLevel(logging.WARNING)
log = logging.getLogger("manager")
for _name in auth.legacyVariables():
    log.warning("%s is no longer read (accounts live in the database): remove it from .env", _name)

@asynccontextmanager
async def lifespan(application: FastAPI):
    """Start the pool sampler with the application, stop it with it."""
    task = asyncio.create_task(sampler.run())
    try:
        yield
    finally:
        task.cancel()
        # Cancelled on purpose: waiting for it to finish is the point, its
        # CancelledError is the expected end.
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="SIP Media Gateway Manager", docs_url=None, redoc_url=None, lifespan=lifespan)

# Lab and production run the same image with the same defaults, and a warning
# in a log is not how a misconfiguration gets noticed. In production the
# defaults that are fine for a lab become a refusal to start: a console that
# will not come up is seen within the minute, one that came up insecure is
# seen after the incident.
production = os.getenv("MANAGER_ENV", "lab").lower() == "production"

sessionSecret = os.getenv("MANAGER_SESSION_SECRET", "")
if not sessionSecret:
    if production:
        raise SystemExit("MANAGER_ENV=production requires MANAGER_SESSION_SECRET: "
                         "sessions would not survive a restart")
    # Ephemeral secret: sessions do not survive a restart. Acceptable for a lab.
    sessionSecret = secrets.token_hex(32)
    log.warning("MANAGER_SESSION_SECRET not set — using an ephemeral secret, "
                "sessions will not survive a restart")

cookieSecure = os.getenv("MANAGER_COOKIE_SECURE", "") == "1"
if production and not cookieSecure:
    raise SystemExit("MANAGER_ENV=production requires MANAGER_COOKIE_SECURE=1: "
                     "the session cookie would travel in clear")

app.add_middleware(
    SessionMiddleware,
    secret_key=sessionSecret,
    session_cookie="gwm_session",
    # Sliding (re-issued on every response); the absolute limit is in auth.
    max_age=auth.SESSION_HOURS * 3600,
    same_site="lax",
    # HTTP-only deployment by default; set MANAGER_COOKIE_SECURE=1 when the
    # optional TLS reverse proxy is in front.
    https_only=cookieSecure,
)

# The service's name, tagline, logo and tab icon, set by the deployment the way
# interact takes its own from brand.js: MANAGER_BRAND_NAME, _TAGLINE, and
# MANAGER_BRAND_LOGO / MANAGER_BRAND_FAVICON, file names in brand/. The
# repository ships SIPMediaGW's own there (logo.svg, favicon.svg, the files of
# the upstream repository), which .env.example names; a deployment adds its
# files beside them. Only the two files named are served, by /brand/<name>.
BRAND_DIR = os.path.join(os.path.dirname(__file__), "brand")
LOGO_TYPES = {".svg": "image/svg+xml", ".png": "image/png", ".jpg": "image/jpeg",
              ".jpeg": "image/jpeg", ".webp": "image/webp", ".ico": "image/x-icon"}


def brandFile(variable: str) -> str:
    """The file a MANAGER_BRAND_* variable names in brand/, or "" when unset or unusable."""
    name = os.getenv(variable, "").strip()
    if not name:
        return ""
    if os.path.basename(name) != name or os.path.splitext(name)[1].lower() not in LOGO_TYPES:
        log.warning("%s=%r is not a file name ending in %s: ignored", variable, name, ", ".join(LOGO_TYPES))
        return ""
    if not os.path.isfile(os.path.join(BRAND_DIR, name)):
        log.warning("%s=%r: no such file in %s", variable, name, BRAND_DIR)
    return name


brandName = os.getenv("MANAGER_BRAND_NAME", "").strip() or "SIP Media Gateway Manager"
brandTagline = os.getenv("MANAGER_BRAND_TAGLINE", "").strip()
brandLogo = brandFile("MANAGER_BRAND_LOGO")
# The tab shows the logo when no icon is named.
brandFavicon = brandFile("MANAGER_BRAND_FAVICON") or brandLogo


def brandUrl(name: str) -> str:
    return f"/brand/{name}" if name else ""


if "MANAGER_BRANDING" in os.environ:          # replaced by the three above
    log.warning("MANAGER_BRANDING is no longer read: MANAGER_BRAND_NAME, _TAGLINE and _LOGO "
                "set the name and the logo; remove it from .env")


class SecurityHeaders(BaseHTTPMiddleware):
    """
    Strict CSP: the front is ES modules and external CSS with no inline code,
    so 'self' is enough. Connector icons are same-origin; the theme toggle and
    charts set styles through the CSSOM, which CSP permits.
    """
    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; "
            "base-uri 'self'; form-action 'self'")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        # Front assets change without a version in their URL, so the browser
        # must ask before reusing a copy: no-cache. It may then get a 304 from
        # the ETag StaticFiles sets — no-store forced the whole file every time.
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-cache"
        response.headers.setdefault("Referrer-Policy", "same-origin")
        return response


class SameOriginWrites(BaseHTTPMiddleware):
    """A write from another origin of the same site is refused (see origin.py)."""
    async def dispatch(self, request, call_next):
        reason = origin.refusal(request.method, request.url.path, request.headers, auth.trustProxy)
        if reason:
            log.warning("write refused, %s: %s %s", reason, request.method, request.url.path)
            return JSONResponse(status_code=403, content={"detail": "Cross-origin write refused"})
        return await call_next(request)


# Inside SecurityHeaders, so that a refusal carries the same headers.
app.add_middleware(SameOriginWrites)
app.add_middleware(SecurityHeaders)
# Outermost: the id must exist before anything below logs or answers.
app.add_middleware(requestid.RequestIdMiddleware)


@app.exception_handler(DatabaseUnavailable)
async def databaseUnavailable(request: Request, exc: DatabaseUnavailable):
    # The full error is already logged by db.py; the client gets no SQL text.
    return JSONResponse(status_code=503,
                        content={"detail": "Reporting database unavailable"})


app.include_router(parkRouter, prefix="/api")
app.include_router(usage.router, prefix="/api")
app.include_router(quality.router, prefix="/api")
app.include_router(pool.router, prefix="/api")
app.include_router(calls.router, prefix="/api")
app.include_router(users.router, prefix="/api")
app.include_router(org_units.router, prefix="/api")
app.include_router(audit.router, prefix="/api")
# Ingestion is machine-to-machine: no prefix, its own bearer token, no session.
app.include_router(ingestRouter)


@app.post("/auth/login")
async def login(request: Request):
    if auth.loginThrottled(request):
        raise HTTPException(status_code=429, detail="Too many attempts, retry in a minute")
    # JSON only: a form or text/plain body is what another page can post
    # without the browser asking first (login CSRF).
    if request.headers.get("content-type", "").split(";")[0].strip().lower() != "application/json":
        raise HTTPException(status_code=415, detail="Expected application/json")
    try:
        body = await request.json()
    except ValueError:                        # malformed JSON: an empty attempt
        body = {}
    # Anything but an object, or a password that is not text, is an empty
    # attempt too: `[]` or {"password": 1} answered 500 and went uncounted.
    if not isinstance(body, dict):
        body = {}
    username = str(body.get("username", "") or auth.ADMIN_USER).strip()
    password = body.get("password", "")
    if not isinstance(password, str):
        password = ""  # nosec B105 - an empty field, not a credential
    # The account lookup and scrypt run in a thread. On the event loop they
    # held every other request for their duration — the park view and the
    # sampler included — and for seconds when the database did not answer.
    account = await run_in_threadpool(auth.authenticate, username, password)
    if account is None:
        auth.recordLoginFailure(request, username)
        raise HTTPException(status_code=401, detail="Invalid username or password")
    auth.clearLoginFailures(request)
    auth.openSession(request, account)
    await run_in_threadpool(auth.recordSignIn, account)
    if account["role"] == auth.ROLE_ADMIN:
        # An account with every right: each use is worth a line.
        log.warning("administrator %s signed in from %s", account["username"], auth.clientIp(request))
    return {"status": "success", "user": account["username"], "role": account["role"],
            "source": account["source"], "must_change_password": account["must_change_password"],
            "password_min_length": auth.MIN_PASSWORD_LENGTH}


@app.post("/auth/logout")
async def logout(request: Request):
    await run_in_threadpool(auth.closeSession, request)
    return {"status": "success"}


@app.get("/health")
async def health():
    """
    Liveness and readiness in one probe, for the container healthcheck.

    A process that is alive but cannot reach its database is not healthy: the
    console would load and every page would show 503. The query is trivial and
    the timeout short, so the probe itself never becomes the thing that hangs.
    """
    try:
        await asyncio.wait_for(asyncio.to_thread(fetch, "SELECT 1"), timeout=3)
    except Exception as exc:                      # DatabaseUnavailable, timeout
        log.warning("health probe failed: %s", exc)
        return JSONResponse(status_code=503, content={"status": "degraded",
                                                      "database": "unreachable"})
    return {"status": "ok"}


@app.get("/api/me")
async def me(request: Request):
    # interact is served by the proxy, not by the Manager: the front gets the
    # base URL from here rather than guessing its own origin.
    # Verified against the table: a session whose account was disabled or
    # whose password changed elsewhere reads as signed out here.
    account = await run_in_threadpool(auth.sessionAccount, request)
    return {
        "authenticated": account is not None,
        "user": account["username"] if account else None,
        "role": account["role"] if account else None,
        "source": account["source"] if account else None,
        "must_change_password": account["must_change_password"] if account else False,
        "password_min_length": auth.MIN_PASSWORD_LENGTH,
        "interact_url": source("proxyapi")["public_url"] + "/interact",
        "brand": {"name": brandName, "tagline": brandTagline,
                  "logo": brandUrl(brandLogo), "favicon": brandUrl(brandFavicon)},
    }


@app.get("/")
async def index():
    path = os.path.join(FRONT_DIR, "index.html")
    if not os.path.isfile(path):
        return JSONResponse(status_code=500, content={"detail": "front/index.html not found"})
    # Read from the mounted volume on every request, so editing the front is
    # live; no-store keeps the browser from serving a stale copy.
    return FileResponse(path, media_type="text/html",
                        headers={"Cache-Control": "no-store"})


@app.get("/brand/{name}")
async def brandFileRoute(name: str):
    """The configured logo and tab icon, and only them: the rest of brand/ is not served."""
    path = os.path.join(BRAND_DIR, name)
    if not name or name not in (brandLogo, brandFavicon) or not os.path.isfile(path):
        return JSONResponse(status_code=404, content={"detail": "Not found"})
    return FileResponse(path, media_type=LOGO_TYPES[os.path.splitext(name)[1].lower()],
                        headers={"Cache-Control": "no-cache"})


# Front assets: nothing secret here, and StaticFiles handles media types,
# ranges and 404s instead of a hand-written whitelist.
app.mount("/static", StaticFiles(directory=FRONT_DIR), name="static")


if __name__ == "__main__":
    # All interfaces: inside a container, the published port decides who reaches it.
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("MANAGER_PORT", "8200")))  # nosec B104
