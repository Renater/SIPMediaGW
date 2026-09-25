"""
Entities (org units) and the rules that attach a calling endpoint to one.

Rules match the CALLING side only, on two fields: its SIP URI (user@domain,
no scheme) and its alias (display name). A rule is a literal prefix or
suffix, case-insensitive: "1test" does not start with "test", ABC = aBc. A
number is a URI prefix, a domain a URI suffix. The list is read top to
bottom and the last rule that matches decides, as in an Expressway
transform list.

Writes are for administrators. Each one is written to org_unit_audit in the
same statement as the change — who, what, when, before and after — so a
change without its line cannot exist. New calls follow the rules at once; the
history is reclassified only when an administrator asks for it, so a report
already sent does not move while the rules are being adjusted.
"""

import json
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from auth import clientIp, requireAdmin
from db import execute, fetch

log = logging.getLogger("manager.org_units")

router = APIRouter()

CODE = re.compile(r"^[A-Z0-9][A-Z0-9_-]{0,31}$")
FIELDS = ("uri", "alias")
MATCH_TYPES = ("prefix", "suffix")          # regex is read, never written here


class NewUnit(BaseModel):
    code: str
    label: str


class UnitPatch(BaseModel):
    label: str | None = None
    active: bool | None = None


class RuleBody(BaseModel):
    org_unit_code: str
    field: str
    match_type: str
    pattern: str
    description: str
    active: bool = True


class RuleOrder(BaseModel):
    ids: list[int]


class Probe(BaseModel):
    uri: str | None = None
    alias: str | None = None


def text(value, what, limit):
    """Required, trimmed of nothing: a leading space in a pattern is a mistake
    that would silently match nothing, so it is refused rather than fixed."""
    if value is None or not value.strip():
        raise HTTPException(status_code=400, detail=f"{what} is required")
    if value != value.strip():
        raise HTTPException(status_code=400, detail=f"{what} must not start or end with a space")
    if len(value) > limit:
        raise HTTPException(status_code=400, detail=f"{what}: {limit} characters at most")
    return value


def checkRule(body: RuleBody):
    if body.field not in FIELDS:
        raise HTTPException(status_code=400, detail=f"field must be one of {', '.join(FIELDS)}")
    if body.match_type not in MATCH_TYPES:
        raise HTTPException(status_code=400, detail=f"match_type must be one of {', '.join(MATCH_TYPES)}")
    return (text(body.pattern, "pattern", 128), text(body.description, "description", 200))


def written(rows, what):
    """A write that touched nothing: the target does not exist."""
    if not rows:
        raise HTTPException(status_code=404, detail=f"no such {what}")
    return rows[0]


# ------------------------------------------------------------------ reading

@router.get("/org-units")
def listUnits(user: str = Depends(requireAdmin)):
    """Entities with their counts, the rules in evaluation order, and how many
    calls no rule claims — what is left to classify."""
    units = fetch("""
        SELECT u.code, u.label, u.active,
               (SELECT count(*) FROM org_unit_rules r WHERE r.org_unit_code = u.code) AS rules,
               (SELECT count(*) FROM calls c WHERE c.org_unit = u.code) AS calls
          FROM org_units u ORDER BY u.code
    """)
    rules = fetch("""
        SELECT id, org_unit_code, field, match_type, pattern, comment AS description,
               active, position, updated_at, updated_by
          FROM org_unit_rules ORDER BY position NULLS FIRST, id
    """)
    unassigned = fetch("SELECT count(*) AS calls FROM calls WHERE org_unit IS NULL")
    return {"units": units, "rules": rules,
            "unassigned": unassigned[0]["calls"] if unassigned else 0}


@router.post("/org-unit-rules/test")
def testRules(body: Probe, user: str = Depends(requireAdmin)):
    """
    Which rule decides for a given caller, and every rule that matched on the
    way: what the console shows before anyone reorders the list.
    """
    rows = fetch("""
        SELECT r.id, r.org_unit_code, r.field, r.match_type, r.pattern, r.position, u.active AS unit_active
          FROM org_unit_rules r JOIN org_units u ON u.code = r.org_unit_code
         WHERE r.active
           AND org_unit_rule_matches(r.match_type, r.pattern,
                                     org_unit_value(r.field, org_unit_uri(%s, NULL, NULL), %s))
         ORDER BY r.position NULLS FIRST, r.id
    """, (body.uri or None, body.alias or None))
    deciding = [row for row in rows if row["unit_active"]]
    return {"matches": rows, "winner": deciding[-1] if deciding else None}


# ------------------------------------------------------------------ entities

@router.post("/org-units", status_code=201)
def createUnit(body: NewUnit, request: Request, user: str = Depends(requireAdmin)):
    code = body.code.strip().upper()
    if not CODE.match(code):
        raise HTTPException(status_code=400, detail="code: capitals, digits, - and _, 32 characters at most")
    label = text(body.label, "label", 80)
    if fetch("SELECT 1 FROM org_units WHERE code = %s", (code,)):
        raise HTTPException(status_code=409, detail="this code already exists")
    row = written(execute("""
        WITH created AS (
            INSERT INTO org_units (code, label) VALUES (%s, %s) RETURNING code, label, active
        ), logged AS (
            INSERT INTO org_unit_audit (actor, action, target, detail)
            SELECT %s, 'unit_create', code, jsonb_build_object('after', to_jsonb(created)) FROM created
        )
        SELECT * FROM created
    """, (code, label, user)), "entity")
    log.info("entity %s created by %s from %s", code, user, clientIp(request))
    return row


@router.put("/org-units/{code}")
def updateUnit(code: str, body: UnitPatch, request: Request, user: str = Depends(requireAdmin)):
    label = text(body.label, "label", 80) if body.label is not None else None
    row = written(execute("""
        WITH changed AS (
            UPDATE org_units u SET label = COALESCE(%s, u.label), active = COALESCE(%s, u.active)
              FROM org_units o WHERE u.code = %s AND o.code = u.code
            RETURNING u.code, u.label, u.active, to_jsonb(o) AS before
        ), logged AS (
            INSERT INTO org_unit_audit (actor, action, target, detail)
            SELECT %s, 'unit_update', code,
                   jsonb_build_object('before', before,
                                      'after', jsonb_build_object('code', code, 'label', label, 'active', active))
              FROM changed
        )
        SELECT code, label, active FROM changed
    """, (label, body.active, code, user)), "entity")
    log.info("entity %s updated by %s from %s", code, user, clientIp(request))
    return row


# ------------------------------------------------------------------ rules

def knownUnit(code):
    if not fetch("SELECT 1 FROM org_units WHERE code = %s", (code,)):
        raise HTTPException(status_code=400, detail="no such entity")


def duplicate(field, matchType, pattern, exceptId=None):
    """Case does not count in matching, so "@Sample.org" and "@sample.org" are
    the same rule."""
    rows = fetch("""
        SELECT id FROM org_unit_rules
         WHERE field = %s AND match_type = %s AND lower(pattern) = lower(%s) AND id IS DISTINCT FROM %s
    """, (field, matchType, pattern, exceptId))
    if rows:
        raise HTTPException(status_code=409, detail=f"the same rule already exists (rule {rows[0]['id']})")


@router.post("/org-unit-rules", status_code=201)
def createRule(body: RuleBody, request: Request, user: str = Depends(requireAdmin)):
    """A new rule goes to the bottom of the list: it wins over every rule
    above it, which is what one adding a rule usually means."""
    pattern, description = checkRule(body)
    knownUnit(body.org_unit_code)
    duplicate(body.field, body.match_type, pattern)
    row = written(execute("""
        WITH created AS (
            INSERT INTO org_unit_rules (org_unit_code, field, match_type, pattern, comment, active,
                                        position, updated_at, updated_by)
            VALUES (%s, %s, %s, %s, %s, %s,
                    (SELECT COALESCE(max(position), 0) + 1 FROM org_unit_rules), now(), %s)
            RETURNING id, org_unit_code, field, match_type, pattern, comment AS description, active, position
        ), logged AS (
            INSERT INTO org_unit_audit (actor, action, target, detail)
            SELECT %s, 'rule_create', 'rule ' || id, jsonb_build_object('after', to_jsonb(created)) FROM created
        )
        SELECT * FROM created
    """, (body.org_unit_code, body.field, body.match_type, pattern, description, body.active,
          user, user)), "rule")
    log.info("rule %s created by %s from %s", row["id"], user, clientIp(request))
    return row


@router.put("/org-unit-rules/{ruleId}")
def updateRule(ruleId: int, body: RuleBody, request: Request, user: str = Depends(requireAdmin)):
    pattern, description = checkRule(body)
    knownUnit(body.org_unit_code)
    duplicate(body.field, body.match_type, pattern, ruleId)
    row = written(execute("""
        WITH changed AS (
            UPDATE org_unit_rules r
               SET org_unit_code = %s, field = %s, match_type = %s, pattern = %s, comment = %s,
                   active = %s, updated_at = now(), updated_by = %s
              FROM org_unit_rules o WHERE r.id = %s AND o.id = r.id
            RETURNING r.id, r.org_unit_code, r.field, r.match_type, r.pattern, r.comment AS description,
                      r.active, r.position, to_jsonb(o) AS before
        ), logged AS (
            INSERT INTO org_unit_audit (actor, action, target, detail)
            SELECT %s, 'rule_update', 'rule ' || id,
                   jsonb_build_object('before', before, 'after', to_jsonb(changed) - 'before')
              FROM changed
        )
        SELECT id, org_unit_code, field, match_type, pattern, description, active, position FROM changed
    """, (body.org_unit_code, body.field, body.match_type, pattern, description, body.active,
          user, ruleId, user)), "rule")
    log.info("rule %s updated by %s from %s", ruleId, user, clientIp(request))
    return row


@router.delete("/org-unit-rules/{ruleId}")
def deleteRule(ruleId: int, request: Request, user: str = Depends(requireAdmin)):
    written(execute("""
        WITH removed AS (
            DELETE FROM org_unit_rules WHERE id = %s RETURNING *
        ), logged AS (
            INSERT INTO org_unit_audit (actor, action, target, detail)
            SELECT %s, 'rule_delete', 'rule ' || id, jsonb_build_object('before', to_jsonb(removed))
              FROM removed
        )
        SELECT id FROM removed
    """, (ruleId, user)), "rule")
    log.info("rule %s deleted by %s from %s", ruleId, user, clientIp(request))
    return {"deleted": ruleId}


@router.put("/org-unit-rules-order")
def orderRules(body: RuleOrder, request: Request, user: str = Depends(requireAdmin)):
    """
    The whole list, top to bottom. Partial lists are refused: two consoles
    reordering at once would otherwise interleave, and the order is the one
    thing that decides.
    """
    current = [row["id"] for row in fetch("SELECT id FROM org_unit_rules ORDER BY position NULLS FIRST, id")]
    if sorted(body.ids) != sorted(current) or len(set(body.ids)) != len(body.ids):
        raise HTTPException(status_code=409, detail="the list changed meanwhile: reload")
    execute("""
        WITH wanted AS (
            SELECT id, ordinality::int AS position FROM unnest(%s::bigint[]) WITH ORDINALITY AS t(id)
        ), before AS (
            SELECT jsonb_agg(id ORDER BY position NULLS FIRST, id) AS ids FROM org_unit_rules
        ), changed AS (
            UPDATE org_unit_rules r SET position = w.position, updated_at = now(), updated_by = %s
              FROM wanted w WHERE r.id = w.id AND r.position IS DISTINCT FROM w.position
            RETURNING r.id
        )
        INSERT INTO org_unit_audit (actor, action, target, detail)
        SELECT %s, 'rules_order', 'rules',
               jsonb_build_object('before', (SELECT ids FROM before), 'after', to_jsonb(%s::bigint[]))
         WHERE EXISTS (SELECT 1 FROM changed)
        RETURNING id
    """, (body.ids, user, user, body.ids))
    log.info("rules reordered by %s from %s", user, clientIp(request))
    return {"order": body.ids}


@router.post("/org-units/recompute")
def recompute(request: Request, user: str = Depends(requireAdmin)):
    """Apply the current rules to the whole history, and say how many calls moved."""
    rows = execute("""
        WITH run AS (SELECT * FROM recompute_org_units(%s)),
        logged AS (
            INSERT INTO org_unit_audit (actor, action, target, detail)
            SELECT %s, 'recompute', 'calls',
                   jsonb_build_object('rows_seen', rows_seen, 'rows_moved', rows_moved) FROM run
        )
        SELECT rows_seen, rows_moved FROM run
    """, (f"console, by {user}", user))
    log.info("org units recomputed by %s from %s: %s", user, clientIp(request), json.dumps(rows[0] if rows else {}))
    return rows[0] if rows else {"rows_seen": 0, "rows_moved": 0}
