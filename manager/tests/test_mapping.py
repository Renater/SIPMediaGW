"""Replay a real gateway payload through the mapping."""
import json
from pathlib import Path

import pytest

from ingest.mapping import callRow, mediaRows

REAL = json.loads((Path(__file__).parent / 'fixtures' / 'payload.json').read_text())

def test_call_row_from_real_payload():
    row = callRow(REAL)
    assert row["call_id"] == "2107293265c8f584671b63541f1f216f"
    assert row["gw_alias"] == "0.mediagw.0"
    assert row["platform"] == "visio"
    assert row["room"] == "wqpmzrtkcx"
    assert row["main_app"] == "baresip"
    assert row["source_number"] == "test"
    assert row["source_domain"] == "sip.sample.org"
    assert row["destination_domain"] == "visio.sample.org"
    assert row["duration_s"] == 30 and row["occupancy_s"] == 30
    assert row["call_start"].isoformat() == "2026-09-04T16:29:47+00:00"
    assert row["call_end"].isoformat() == "2026-09-04T16:30:17+00:00"
    assert row["close_reason"].startswith("Connection reset by peer")

def test_empty_strings_become_null():
    row = callRow(REAL)
    assert row["source_name"] is None      # "" in the payload
    assert row["call_url"] is None         # "" in the payload
    assert row["destination_room"] is None

def test_media_rows_cover_audio_and_every_video_stream():
    rows = mediaRows(REAL["call"]["mediaStats"])
    assert len(rows) == 6                  # audio tx/rx + 2 video streams tx/rx
    keys = {(r["media"], r["stream_index"], r["direction"]) for r in rows}
    assert keys == {("audio",0,"tx"), ("audio",0,"rx"),
                    ("video",0,"tx"), ("video",0,"rx"),
                    ("video",1,"tx"), ("video",1,"rx")}
    audioRx = next(r for r in rows if r["media"]=="audio" and r["direction"]=="rx")
    assert audioRx["packets"] == 1485 and audioRx["lost_packets"] == 6
    assert audioRx["jitter_ms"] == 1.0 and audioRx["avg_bitrate_kbps"] == 13.9
    video0Tx = next(r for r in rows if r["media"]=="video" and r["stream_index"]==0 and r["direction"]=="tx")
    assert video0Tx["packets"] == 5604 and video0Tx["avg_bitrate_kbps"] == 1726.9

def test_media_rows_tolerate_missing_or_partial_stats():
    assert mediaRows(None) == []
    assert mediaRows({}) == []
    rows = mediaRows({"audio": {"tx": {"packets": 5}}})   # rx missing
    assert len(rows) == 1 and rows[0]["direction"] == "tx"
    assert rows[0]["jitter_ms"] is None

def test_video_as_single_object_is_tolerated():
    rows = mediaRows({"video": {"streamIndex": 0, "tx": {"packets": 1}}})
    assert len(rows) == 1 and rows[0]["media"] == "video"

def test_invalid_documents_are_rejected():
    for bad in ([], "x", {}, {"call": "nope"}):
        with pytest.raises(ValueError):
            callRow(bad)

def test_seconds_fall_back_to_milliseconds():
    payload = json.loads(json.dumps(REAL))
    del payload["call"]["callSession"]["totalTime"]["seconds"]
    assert callRow(payload)["duration_s"] == 30
