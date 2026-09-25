"""
Guard against the outcome rules drifting apart.

The classification lives twice in SQL: once in the BEFORE INSERT trigger, which
works on NEW, and once in recompute_outcomes(), which works on a set. The
duplication is deliberate — the two contexts cannot share a single expression —
but nothing stops someone from changing one and forgetting the other, and the
symptom would be a history that no longer matches what the trigger produces.

These tests read both SQL bodies and check they name the same branches in the
same order. They cannot execute SQL, so they prove the shapes agree, not the
results; running recompute_outcomes() on a freshly ingested row and finding it
unchanged is the check that proves the results, and it belongs in the
deployment procedure rather than here.
"""

import re
from pathlib import Path

import pytest

DB = Path(__file__).resolve().parent.parent / "db"
SCHEMA = DB / "schema.sql"
LOT0 = DB / "schema_reporting_lot0.sql"


def body(path, marker, stop):
    text = path.read_text()
    start = text.index(marker)
    return text[start:text.index(stop, start)]


@pytest.fixture(scope="module")
def triggerRule():
    return body(SCHEMA, "CREATE OR REPLACE FUNCTION calls_set_outcome", "END $$;")


@pytest.fixture(scope="module")
def recomputeRule():
    return body(LOT0, "CREATE OR REPLACE FUNCTION recompute_outcomes", "RETURN QUERY")


def branches(sql):
    """The outcome values assigned, in the order the SQL assigns them."""
    return re.findall(r"'(not_established|completed|failed|ivr_only)'", sql)


def test_both_rules_assign_the_same_outcomes_in_the_same_order(triggerRule, recomputeRule):
    """
    The two bodies must name the same outcomes in the same order. Both end with
    a second mention of 'completed', where duration_s is set from the outcome —
    comparing the full sequence therefore also catches a divergence there.
    """
    assert branches(triggerRule) == branches(recomputeRule)
    assert branches(triggerRule)[:4] == ['not_established', 'completed', 'failed', 'ivr_only']


def test_both_rules_test_establishment_before_anything_else(triggerRule, recomputeRule):
    """A call that never came up has no room and often a technical reason
    ("Invalid argument"): tested first, it is not_established, not failed."""
    for sql in (triggerRule, recomputeRule):
        establishedAt = re.search(r"NOT (NEW\.)?established", sql).start()
        assert establishedAt < sql.index('room IS NOT NULL')
        assert establishedAt < sql.index('is_technical_failure')


def test_the_trigger_dates_a_call_without_start_by_its_reception(triggerRule):
    assert re.search(r"NEW\.call_start\s*:=\s*NEW\.received_at", triggerRule)
    assert re.search(r"NEW\.established\s*:=\s*false", triggerRule)


def test_both_rules_test_a_room_first(triggerRule, recomputeRule):
    """A joined conference wins over any close reason: a call that reached a room
    completed, whatever went wrong afterwards."""
    for sql in (triggerRule, recomputeRule):
        roomAt = sql.index('room')
        failureAt = sql.index('is_technical_failure')
        assert roomAt < failureAt


def test_both_rules_delegate_the_failure_list(triggerRule, recomputeRule):
    """Neither may inline the patterns: the whitelist is enriched from production,
    and a copy would be forgotten."""
    for sql in (triggerRule, recomputeRule):
        assert 'is_technical_failure' in sql
        assert 'LIKE' not in sql.upper()


def test_duration_follows_the_outcome_in_both(triggerRule, recomputeRule):
    """Gateway time is consumed whatever happens; call duration only counts when
    a conference was joined. The rule exists in both places or the recompute
    would leave duration_s inconsistent with outcome."""
    for sql in (triggerRule, recomputeRule):
        assert 'duration_s' in sql
        assert "completed" in sql


def test_the_whitelist_is_a_prefix_match_on_six_patterns():
    """
    Documents what the list holds today. It is expected to grow: when it does,
    this count changes and recompute_outcomes() must be run — which is the
    reason the test names the number rather than hiding it.
    """
    fn = body(SCHEMA, "CREATE OR REPLACE FUNCTION is_technical_failure", "$$;")
    patterns = re.findall(r"p_reason LIKE '([^']+)'", fn)
    assert len(patterns) == 6, f"the allow-list changed: {patterns}"
    assert all(p.endswith('%') for p in patterns), "the patterns are prefixes"
