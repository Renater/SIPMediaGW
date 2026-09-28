"""
The call history a gateway pushes at the end of a call is a contract with the
Manager: manager/tests/fixtures/push.schema.json describes it, the Manager
checks its real pushes against it, and this test checks what logParse builds
from a fixed history file against the same file. A key renamed here fails
before it empties a report there.
"""
import importlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads((ROOT / "manager" / "tests" / "fixtures" / "push.schema.json").read_text())
HISTORY = (Path(__file__).parent / "fixtures" / "history_call.log").read_text().splitlines(keepends=True)

TYPES = {"object": dict, "array": list, "string": str, "integer": int, "number": (int, float), "boolean": bool}


def problems(value, schema, path="$"):
    """Every departure of `value` from `schema` (the subset of JSON Schema the file uses)."""
    if "$ref" in schema:
        target = SCHEMA
        for part in schema["$ref"].lstrip("#/").split("/"):
            target = target[part]
        return problems(value, target, path)
    found = []
    expected = schema.get("type")
    if expected:
        if not isinstance(value, TYPES[expected]) or (expected in ("integer", "number") and isinstance(value, bool)):
            return [f"{path}: expected {expected}, got {type(value).__name__}"]
    if isinstance(value, dict):
        found += [f"{path}.{name}: required" for name in schema.get("required", ()) if name not in value]
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


def build():
    sys.path.insert(0, str(ROOT / "src"))
    sys.modules.pop("logParse", None)
    return importlib.import_module("logParse").buildPayloadFromLines(HISTORY, "http://manager.example/ingest/calls")


def test_the_payload_matches_the_shared_schema():
    assert problems(build(), SCHEMA) == []


def test_the_fields_the_manager_counts_on_are_filled():
    call = build()["call"]
    # GW_ID is the container slot (0, 1...), not the proxy registration id:
    # the gateway is named by details.destination.destinationGw.
    assert "gwId" not in call
    assert call["mainApp"] == "baresip" and call["browsing"] == "visio" and call["room"] == "wqpmzrtkcx"
    assert call["details"]["callId"] == "1fb3a50b017ee6be6caed888b6cf2729"
    assert call["callSession"]["callStart"]["timestamp"] == "2026-09-24T08:20:48Z"
    assert call["callSession"]["totalTime"]["seconds"] == 38
    assert call["details"]["closeReason"] == "Connection reset by peer [104]"
    assert call["details"]["peerUserAgent"].startswith("TANDBERG")
    assert call["mediaStats"]["samples"][0]["seconds"] == 10.0
