"""
The push contract, written once in tests/fixtures/push.schema.json: what a
gateway sends at the end of a call and what ingest/mapping.py reads. The
fixtures are real pushes, so the schema is checked against reality here; the
gateway's own suite checks the payload it builds against the same file. A key
renamed on either side fails a suite before it empties a report.

The validator below covers the subset of JSON Schema the file uses, so that
the test image needs no extra package.
"""

import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
SCHEMA = json.loads((FIXTURES / "push.schema.json").read_text())

TYPES = {"object": dict, "array": list, "string": str, "integer": int, "number": (int, float), "boolean": bool}


def problems(value, schema, path="$"):
    """Every way `value` departs from `schema`, as 'path: reason' lines."""
    if "$ref" in schema:
        target = SCHEMA
        for part in schema["$ref"].lstrip("#/").split("/"):
            target = target[part]
        return problems(value, target, path)
    found = []
    expected = schema.get("type")
    if expected:
        kind = TYPES[expected]
        if not isinstance(value, kind) or (expected in ("integer", "number") and isinstance(value, bool)):
            return [f"{path}: expected {expected}, got {type(value).__name__}"]
    if isinstance(value, dict):
        for name in schema.get("required", ()):
            if name not in value:
                found.append(f"{path}.{name}: required")
        for name, sub in schema.get("properties", {}).items():
            if name in value:
                found += problems(value[name], sub, f"{path}.{name}")
        extra = schema.get("additionalProperties")
        if isinstance(extra, dict):
            for name, item in value.items():
                if name not in schema.get("properties", {}):
                    found += problems(item, extra, f"{path}.{name}")
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            found += problems(item, schema["items"], f"{path}[{index}]")
    if isinstance(value, str) and "pattern" in schema and not re.search(schema["pattern"], value):
        found.append(f"{path}: {value!r} does not match {schema['pattern']}")
    if isinstance(value, (int, float)) and "minimum" in schema and value < schema["minimum"]:
        found.append(f"{path}: {value} below {schema['minimum']}")
    return found


@pytest.mark.parametrize("name", sorted(p.name for p in FIXTURES.glob("payload*.json")))
def test_every_real_push_matches_the_schema(name):
    payload = json.loads((FIXTURES / name).read_text())
    assert problems(payload, SCHEMA) == [], name


def test_the_validator_refuses_what_the_ingest_would_misread():
    """Not a rubber stamp: the departures the Manager cannot recover from are caught."""
    good = json.loads((FIXTURES / "payload_media.json").read_text())
    renamed = json.loads(json.dumps(good))
    renamed["call"]["meeting"] = renamed["call"].pop("room")
    assert any("call.room: required" in line for line in problems(renamed, SCHEMA))
    local = json.loads(json.dumps(good))
    local["call"]["callSession"]["callStart"]["timestamp"] = "2026-09-24T10:20:48+02:00"
    assert any("callStart.timestamp" in line for line in problems(local, SCHEMA))
    text = json.loads(json.dumps(good))
    text["call"]["callSession"]["totalTime"]["seconds"] = "38"
    assert any("totalTime.seconds" in line for line in problems(text, SCHEMA))


def test_every_key_the_mapping_reads_is_in_the_schema():
    """mapping.py reads call.<a>.<b> with .get(): each of those names is declared,
    so that the schema and the reader cannot drift apart unnoticed."""
    source = (ROOT / "ingest" / "mapping.py").read_text()
    body = source[source.index("def callRow("):]
    read = set(re.findall(r'\b(?:call|session|details|source|destination|total)\.get\("(\w+)"\)', body))
    declared = set()

    def walk(node):
        for name, sub in node.get("properties", {}).items():
            declared.add(name)
            walk(sub)
        for sub in node.get("$defs", {}).values():
            walk(sub)
    walk(SCHEMA)
    assert read <= declared, f"read by mapping.py, absent from the schema: {sorted(read - declared)}"
