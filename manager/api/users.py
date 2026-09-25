"""
Accounts: one's own password, and the user list for an administrator.

What an administrator can do to others: create a local account (e-mail as
username, first and last name, role, an initial password to be changed at
first sign-in), reset a password, change a role, disable and re-enable,
delete. What nobody can do to their own account from the console: change
its role, disable it, delete it — a second administrator does that, or
tools/user.py from the server. The last enabled administrator can be
neither demoted, disabled nor deleted: the console must always have a way in.

Every change is written to user_audit — names, roles and flags, never a
password or a hash — in the same transaction as the change itself. A deleted
account keeps its lines there.
"""

import logging
import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

import auth
import users
from auth import clientIp, requireAdmin, requireSession

log = logging.getLogger("manager.users")

router = APIRouter()

# An e-mail address, lower-cased: local part, one @, a domain with a dot.
EMAIL = re.compile(r"^[a-z0-9][a-z0-9._+-]{0,62}@[a-z0-9-]+(\.[a-z0-9-]+)+$")


def public(account) -> dict:
    """What the front sees of an account: never the hash."""
    return {
        "username": account["username"], "first_name": account["first_name"],
        "last_name": account["last_name"], "role": account["role"], "source": account["source"],
        "enabled": account["enabled"], "must_change_password": account["must_change_password"],
        "created_at": account["created_at"], "password_changed_at": account["password_changed_at"],
        "last_login_at": account["last_login_at"],
    }


def cleanName(value, what):
    text = (value or "").strip()
    if not text or len(text) > 80:
        raise HTTPException(status_code=400, detail=f"{what} is required (80 characters at most)")
    return text


# ------------------------------------------------------------ own account

class PasswordChange(BaseModel):
    current: str
    new: str
    confirm: str


@router.post("/account/password")
def changeOwnPassword(body: PasswordChange, request: Request, user: str = Depends(requireSession)):
    """
    The current password, the new one twice. Allowed while a change is
    required — it is the one thing such a session may do. An account that
    comes from an identity provider has no password here.

    Throttled like the sign-in: an open session is not a licence to guess
    the current password, and a guessed one would lock its owner out.
    """
    if auth.loginThrottled(request):
        raise HTTPException(status_code=429, detail="Too many attempts, retry in a minute")
    account = request.state.account
    if account["source"] != "local":
        raise HTTPException(status_code=400, detail="this account signs in through the identity provider")
    if not auth.checkPassword(body.current, account["password_hash"]):
        auth.recordLoginFailure(request, user)
        raise HTTPException(status_code=403, detail="current password is wrong")
    if body.new != body.confirm:
        raise HTTPException(status_code=400, detail="the two new passwords differ")
    problem = auth.passwordProblem(body.new, user, current=body.current)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    updated = users.setPassword(user, auth.hashPassword(body.new), mustChange=False,
                                audit=(user, "password.change", user, {"ip": clientIp(request)}))
    # The epoch moved: this session follows it, every other one of the
    # account is refused on its next request.
    auth.openSession(request, updated)
    # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure -- names and addresses only, never a password
    log.info("password changed by %s from %s", user, clientIp(request))
    return {"status": "success"}


# ------------------------------------------------------------ administration

class NewUser(BaseModel):
    username: str
    first_name: str = ""
    last_name: str = ""
    role: str
    source: str = "local"
    password: str | None = None


class UserPatch(BaseModel):
    role: str | None = None
    enabled: bool | None = None
    first_name: str | None = None
    last_name: str | None = None


class PasswordReset(BaseModel):
    password: str


@router.get("/users")
def readUsers(user: str = Depends(requireAdmin)):
    return [public(row) for row in users.listUsers()]


@router.post("/users", status_code=201)
def createUser(body: NewUser, request: Request, user: str = Depends(requireAdmin)):
    name = body.username.strip().lower()
    if not EMAIL.match(name):
        raise HTTPException(status_code=400, detail="username must be an e-mail address")
    firstName, lastName = cleanName(body.first_name, "first name"), cleanName(body.last_name, "last name")
    if body.role not in users.ROLES:
        raise HTTPException(status_code=400, detail=f"role must be one of {', '.join(users.ROLES)}")
    if body.source not in users.SOURCES:
        raise HTTPException(status_code=400, detail=f"source must be one of {', '.join(users.SOURCES)}")
    if body.source != "local":
        # The option exists so the form can show it; the accounts arrive with
        # the identity provider, which is what gives them their identifier.
        raise HTTPException(status_code=400, detail="ProConnect accounts arrive with the SSO integration")
    problem = auth.passwordProblem(body.password or "", name)
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    if users.getUser(name):
        raise HTTPException(status_code=409, detail="this username already exists")
    created = users.createUser(name, body.role, body.source, auth.hashPassword(body.password or ""),
                               createdBy=user, mustChange=True, firstName=firstName, lastName=lastName,
                               audit=(user, "create", name, {"role": body.role, "source": body.source,
                                                             "name": f"{firstName} {lastName}"}))
    log.info("user %s created by %s (%s)", name, user, body.role)
    return public(created)


def target(name: str):
    account = users.getUser(name)
    if not account:
        raise HTTPException(status_code=404, detail="no such user")
    return account


def lastAdmin(account) -> bool:
    return account["role"] == "admin" and account["enabled"] and users.countActiveAdmins() <= 1


@router.put("/users/{name}")
def updateUser(name: str, body: UserPatch, request: Request, user: str = Depends(requireAdmin)):
    """
    Everything is checked before anything is written, then the changes and
    their audit line go in one statement: a refused role no longer leaves the
    name change of the same request behind, unrecorded.
    """
    account = target(name)
    name = account["username"]
    fields: dict[str, Any] = {}
    changes: dict[str, Any] = {}
    if body.first_name is not None or body.last_name is not None:
        firstName = cleanName(body.first_name if body.first_name is not None else account["first_name"], "first name")
        lastName = cleanName(body.last_name if body.last_name is not None else account["last_name"], "last name")
        if (firstName, lastName) != (account["first_name"], account["last_name"]):
            fields["name"] = (firstName, lastName)
            changes["name"] = f"{firstName} {lastName}"
    if body.role is not None and body.role != account["role"]:
        if body.role not in users.ROLES:
            raise HTTPException(status_code=400, detail=f"role must be one of {', '.join(users.ROLES)}")
        if name == user:
            raise HTTPException(status_code=409, detail="an account cannot change its own role")
        if lastAdmin(account):
            raise HTTPException(status_code=409, detail="the last administrator cannot be demoted")
        fields["role"] = changes["role"] = body.role
    if body.enabled is not None and body.enabled != account["enabled"]:
        if not body.enabled:
            if name == user:
                raise HTTPException(status_code=409, detail="an account cannot disable itself")
            if lastAdmin(account):
                raise HTTPException(status_code=409, detail="the last administrator cannot be disabled")
        fields["enabled"] = changes["enabled"] = body.enabled
    if not fields:
        return public(account)
    updated = users.updateAccount(name, audit=(user, "update", name, changes), **fields)
    if updated is None:                      # deleted between the read and the write
        raise HTTPException(status_code=404, detail="no such user")
    log.info("user %s updated by %s: %s", name, user, changes)
    return public(updated)


@router.post("/users/{name}/password")
def resetPassword(name: str, body: PasswordReset, request: Request, user: str = Depends(requireAdmin)):
    """A new initial password, to be changed by its holder at next sign-in."""
    account = target(name)
    if account["source"] != "local":
        raise HTTPException(status_code=400, detail="this account has no local password")
    problem = auth.passwordProblem(body.password, account["username"])
    if problem:
        raise HTTPException(status_code=400, detail=problem)
    updated = users.setPassword(account["username"], auth.hashPassword(body.password), mustChange=True,
                                audit=(user, "password.reset", account["username"], {}))
    # nosemgrep: python.lang.security.audit.logging.logger-credential-leak.python-logger-credential-disclosure -- names and addresses only, never a password
    log.info("password of %s reset by %s", account["username"], user)
    if account["username"] == user:
        auth.openSession(request, updated)
    return public(updated)


@router.delete("/users/{name}")
def deleteUser(name: str, request: Request, user: str = Depends(requireAdmin)):
    """
    The account goes; its audit lines stay, and the one written here says who
    deleted it. Its open sessions find no row on their next request.
    """
    account = target(name)
    name = account["username"]
    if name == user:
        raise HTTPException(status_code=409, detail="an account cannot delete itself")
    if lastAdmin(account):
        raise HTTPException(status_code=409, detail="the last administrator cannot be deleted")
    users.deleteUser(name, audit=(user, "delete", name, {"role": account["role"], "source": account["source"]}))
    log.warning("user %s deleted by %s", name, user)
    return {"status": "success"}


@router.get("/users/audit")
def readAudit(user: str = Depends(requireAdmin)):
    return users.listAudit()
