"""mediaStats.video carries the end-of-call streams only, whatever the readings."""
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("logParse", ROOT / "src" / "logParse.py")
logParse = importlib.util.module_from_spec(spec)
sys.modules.setdefault("logParse", logParse)  # dataclasses look the module up
spec.loader.exec_module(logParse)

FIELD = next(iter(logParse.fieldMap.values()))


def rec(kind, data):
    return f"{kind}:{json.dumps(data)}"


def video(idx, tx, rx):
    return rec("stats_value", {"media": "video", "streamIndex": idx, "field": FIELD, "tx": tx, "rx": rx})


def reading(first_idx, seconds):
    return [video(first_idx, 100 * seconds, 100 * seconds), video(first_idx + 1, seconds, 0),
            rec("media_sample", {"seconds": seconds, "video": {}})]


def closed():
    return rec("call_closed", {"lastEventType": "CALL_CLOSED", "callId": "abc"})


def payload_video(lines):
    payload = logParse.buildPayloadFromLines(lines, "")
    call = payload.get("call", payload)
    return call["mediaStats"]["video"]


def test_readings_do_not_add_streams():
    # The order seen on a real call: three readings, the call closes, then
    # baresip prints the video block of the call itself.
    lines = reading(1, 10) + reading(3, 21) + reading(5, 32) + [
        rec("stats_value", {"media": "audio", "field": FIELD, "tx": 1810, "rx": 1803}),
        closed(),
        video(7, 7164, 7333),
        video(8, 41, 0),
    ]
    streams = payload_video(lines)
    assert len(streams) == 2
    assert streams[0]["tx"][FIELD] == 7164
    assert streams[0]["rx"][FIELD] == 7333
    assert streams[1]["tx"][FIELD] == 41
    # Numbered as the call's streams, not as the counter left them (7 and 8):
    # the Manager shows the number in the call detail.
    assert [s["streamIndex"] for s in streams] == [0, 1]


def test_reading_cut_short_by_the_hang_up_is_dropped():
    # Tables printed by a reading whose event never came, just before the close.
    lines = reading(1, 10) + [video(3, 999, 999), video(4, 9, 0), closed(),
                              video(5, 7164, 7333), video(6, 41, 0)]
    streams = payload_video(lines)
    assert [s["tx"][FIELD] for s in streams] == [7164, 41]


def test_call_without_readings_is_unchanged():
    lines = [closed(), video(1, 500, 480), video(2, 3, 0)]
    streams = payload_video(lines)
    assert [s["tx"][FIELD] for s in streams] == [500, 3]
    assert [s["streamIndex"] for s in streams] == [1, 2], "numbers kept when nothing drifted"
