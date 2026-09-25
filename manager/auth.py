"""
Single authorization point for the Manager.

Accounts live in the database (users.py); this module hashes and checks
passwords, says what a password must look like, throttles sign-in attempts,
and turns a session cookie into a verified user on every request. Swapping
the sign-in mechanism for an OIDC flow (ProConnect) later touches this module
and users.py, never the views or the relay routes.

A session holds the user name, the account's session_epoch and the time of
sign-in. Every request reads the account back: disabled, or an epoch bumped
by a password change, a role change, a lock-out or a sign-out, and the
session is over. So is one older than SESSION_HOURS, however busy: the
cookie is re-issued on every response, and the park view polls, so without a
limit of its own a session would never end. The
role is read from the account, not from the cookie, so a change of role
takes effect on the next request.
"""

import base64
import hashlib
import hmac
import ipaddress
import logging
import os
import secrets
import time

from fastapi import HTTPException, Request

import users

log = logging.getLogger("manager.auth")

ROLE_ADMIN = "admin"
ROLE_OPERATOR = "operator"
# The account created on an empty user table, and the password it gets.
ADMIN_USER = "admin"
DEFAULT_PASSWORD = os.getenv("MANAGER_DEFAULT_PASSWORD", "manager123$")
# ANSSI: length over composition rules. Configurable, never below 8.
MIN_PASSWORD_LENGTH = max(8, int(os.getenv("PASSWORD_MIN_LENGTH", "11")))
# Longest a session lasts from sign-in, active or not: a working day.
SESSION_HOURS = max(1, int(os.getenv("MANAGER_SESSION_HOURS", "10")))

# --------------------------------------------------------------- passwords

# scrypt from the standard library: no dependency to audit, memory-hard, and
# the parameters travel with the hash so they can be raised later without
# touching stored accounts.
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1


def hashPassword(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=SCRYPT_N, r=SCRYPT_R, p=SCRYPT_P, dklen=32)
    return "scrypt$%d$%d$%d$%s$%s" % (SCRYPT_N, SCRYPT_R, SCRYPT_P,
                                      base64.b64encode(salt).decode(), base64.b64encode(digest).decode())


def checkPassword(password: str, stored) -> bool:
    """Constant-time comparison against a stored hash; False for an account without one."""
    if not stored:
        return False
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        candidate = hashlib.scrypt(password.encode(), salt=base64.b64decode(salt),
                                   n=int(n), r=int(r), p=int(p), dklen=32)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(candidate, base64.b64decode(digest))


# A hash nobody signs in with: an unknown name costs the same as a wrong
# password, so timing does not say which names exist.
_DUMMY_HASH = hashPassword(secrets.token_hex(16))


def passwordProblem(password: str, username: str, current=None):
    """
    Why a password is refused, or None. Length over composition (ANSSI): a
    long passphrase beats a short one with a digit and a symbol.
    """
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LENGTH:
        return f"password must be at least {MIN_PASSWORD_LENGTH} characters"
    if len(password) > 256:
        return "password must be at most 256 characters"
    if password.lower() == (username or "").lower():
        return "password must differ from the username"
    if password == DEFAULT_PASSWORD:
        return "password must differ from the default password"
    if current is not None and password == current:
        return "new password must differ from the current one"
    return None


# ---------------------------------------------------------------- throttle

# Naive in-memory throttle: after maxFailures failed logins from one IP,
# refuse further attempts for lockSeconds. Enough for an internal console;
# resets on process restart.
maxFailures = 5
lockSeconds = 60
_failures: dict[str, list[float]] = {}  # ip -> [count, unlockTimestamp]


# Behind a reverse proxy every connection carries the proxy's address, and a
# throttle keyed on it locks the console for everyone after five failures by
# anyone. The forwarded header is honoured only when the deployment says a
# proxy is in front: read unconditionally, a direct client could forge it and
# step around the throttle.
trustProxy = os.getenv("TRUST_PROXY", "") == "1"


def parseProxies(spec: str):
    """
    FORWARDED_ALLOW_IPS: addresses or networks, comma-separated, or * — the
    same variable uvicorn reads. An entry that is neither is logged and
    skipped rather than stopping the console.
    """
    networks: list = []   # networks, or "*"
    for item in (part.strip() for part in (spec or "").split(",")):
        if not item:
            continue
        if item == "*":
            networks.append("*")
            continue
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            log.warning("FORWARDED_ALLOW_IPS: ignoring %r, not an address or a network", item)
    return networks


# Which peers may speak for the client. The Manager's port stays open on the
# LAN — the gateways push there — so "a proxy is in front" is not enough: a
# host on the LAN talking to the port directly would choose its own address
# and step around the throttle. The header counts only from these peers.
trustedProxies = parseProxies(os.getenv("FORWARDED_ALLOW_IPS", "127.0.0.1"))


def fromTrustedProxy(peer: str) -> bool:
    if "*" in trustedProxies:
        return True
    try:
        address = ipaddress.ip_address(peer)
    except ValueError:
        return False
    return any(address in network for network in trustedProxies if network != "*")


def clientIp(request: Request) -> str:
    """The address to throttle on and to log: proxy-aware when told to be."""
    peer = request.client.host if request.client else "unknown"
    if trustProxy and fromTrustedProxy(peer):
        forwarded = request.headers.get("X-Forwarded-For", "")
        if forwarded:
            # One trusted proxy in front, appending what it saw: the client is
            # the LAST entry. Anything before it was sent by the client itself
            # and is exactly what a throttle must not key on.
            return forwarded.split(",")[-1].strip() or "unknown"
    return peer


def loginThrottled(request: Request) -> bool:
    entry = _failures.get(clientIp(request))
    if not entry:
        return False
    count, unlockAt = entry
    if count < maxFailures:
        return False
    if time.monotonic() >= unlockAt:
        del _failures[clientIp(request)]
        return False
    return True


def recordLoginFailure(request: Request, username: str = ""):
    """
    Counted per address, and logged: the throttle alone leaves no trace of
    someone guessing. %r keeps a crafted name from forging a log line.
    """
    ip = clientIp(request)
    # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure -- the name tried and the address, never the password
    log.warning("wrong password for %r from %s", (username or "")[:80], ip)
    now = time.monotonic()
    # Expired entries go on every insertion: a spray of addresses (forged
    # or not) must not grow this dict for the life of the process.
    for stale in [k for k, (_, unlockAt) in _failures.items() if unlockAt <= now]:
        del _failures[stale]
    count = _failures.get(ip, [0, 0])[0] + 1
    _failures[ip] = [count, now + lockSeconds]


def clearLoginFailures(request: Request):
    _failures.pop(clientIp(request), None)


# ----------------------------------------------------------------- sign-in

def ensureBootstrap():
    """
    An empty user table gets the local admin with the default password, to be
    changed at first sign-in. Nothing else: accounts are created from the
    console, never from the environment.
    """
    if users.countUsers():
        return
    users.createUser(ADMIN_USER, ROLE_ADMIN, "local", hashPassword(DEFAULT_PASSWORD), "bootstrap",
                     audit=("bootstrap", "create", ADMIN_USER, {"role": ROLE_ADMIN, "source": "local"}))
    log.warning("user table was empty: created %r with the default password, to be changed", ADMIN_USER)


# Accounts held in the environment before the user table existed. No longer
# read; named at startup while they linger, so a forgotten line in .env is
# seen rather than mistaken for a working password.
LEGACY_VARIABLES = ("MANAGER_PASSWORD", "MANAGER_OPERATORS")


def legacyVariables():
    """The legacy account variables still present in the environment (names only)."""
    return [name for name in LEGACY_VARIABLES if os.getenv(name) is not None]


def authenticate(username: str, password: str):
    """
    The account for these credentials, or None.

    An unknown, disabled or non-local account takes the same path as a wrong
    password — one scrypt over a real or dummy hash — so timing and answer
    are identical and the form cannot be used to enumerate accounts.
    """
    ensureBootstrap()
    account = users.getUser(username or "")
    usable = account is not None and account["enabled"] and account["source"] == "local"
    ok = checkPassword(password or "", account["password_hash"] if usable else _DUMMY_HASH)
    return account if usable and ok else None


def openSession(request: Request, account):
    request.session["user"] = account["username"]
    request.session["epoch"] = account["session_epoch"]
    request.session["at"] = int(time.time())


def closeSession(request: Request):
    """
    Sign-out. The cookie is signed, not stored: clearing it in this browser
    leaves any copy of it valid. Bumping the epoch ends every session of the
    account. No account is shared between people; the installation admin,
    used at install only, is signed out everywhere, as it should be.
    """
    name = request.session.get("user")
    request.session.clear()
    if name:
        try:
            users.bumpEpoch(name)
        except Exception as exc:                  # database down: this browser is out anyway
            log.warning("sign-out of %s: sessions elsewhere not ended (%s)", name, exc)


def recordSignIn(account):
    """The list shows when an account last signed in: a login, not a password change."""
    users.touchLogin(account["username"])


def sessionAccount(request: Request):
    """
    The account behind the session, verified against the table on every
    request, or None: no session, unknown or disabled account, or an epoch
    bumped since sign-in (password or role changed, account locked).
    """
    name = request.session.get("user")
    if not name:
        return None
    openedAt = request.session.get("at")
    if not isinstance(openedAt, int) or time.time() - openedAt > SESSION_HOURS * 3600:
        request.session.clear()
        return None
    account = users.getUser(name)
    if not account or not account["enabled"] or account["session_epoch"] != request.session.get("epoch"):
        request.session.clear()
        return None
    return account


def requireSession(request: Request):
    """A live session, whether or not the password still has to be changed."""
    account = sessionAccount(request)
    if account is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    request.state.account = account
    return account["username"]


def requireUser(request: Request):
    """
    FastAPI dependency guarding every /api route. An account that must change
    its password can do nothing else first: the front shows that form on a 403
    carrying this detail.
    """
    name = requireSession(request)
    if request.state.account["must_change_password"]:
        raise HTTPException(status_code=403, detail="password change required")
    return name


def requireAdmin(request: Request):
    """Dependency for the routes that write. The role is the account's, now."""
    name = requireUser(request)
    if request.state.account["role"] != ROLE_ADMIN:
        raise HTTPException(status_code=403, detail="Administrator role required")
    return name
