"""
The fields SIPMediaGW pushes since #101 (samples), #102 (peer, encoders,
media direction) and #105 (versions), on real payloads from the lab:

  payload_before_media.json   15/09, none of the new fields
  payload_media.json          24/09, all of them, 3 samples, no presentation
  payload_presentation.json   24/09, a slide presentation from 142 s to 274 s
  payload_not_established.json  a Call-ID, no start: the call never came up
  payload_empty.json          no Call-ID: a container stopped without a call

and on synthetic samples for what the lab never produced (a frozen picture,
one-way video).
"""

import copy
import json
from pathlib import Path

from ingest.mapping import (
    LOW_FPS, callRow, frameRates, isRepeated, looksCumulative, mediaDetails, mediaRows, sampleSummary,
)

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text())


def videoRows(payload):
    return [row for row in mediaRows(payload["call"]["mediaStats"]) if row["media"] == "video"]


# ---------------------------------------------------------------- old payload

def test_an_old_payload_leaves_every_new_column_empty():
    """Absent, not wrong: a call pushed before the new fields keeps NULLs."""
    row = callRow(load("payload_before_media.json"))
    for name in ("peer_user_agent", "audio_codec", "video_codec", "video_encoder",
                 "media_direction", "gw_version", "baresip_version", "baresip_patch",
                 "chromium_version", "video_state", "video_min_rx_fps",
                 "video_low_intervals", "video_keyframe_requests", "presentation_s"):
        assert row[name] is None, name
    assert row["call_id"] == "0465d91c265904636a4736df114c2fad"


def test_an_old_payload_without_samples_keeps_every_video_entry():
    """Without samples, nothing says the entries are repeats: all are kept, as
    before P15 (the backfill handles the 15/09 calls from their counters)."""
    payload = load("payload_before_media.json")
    assert len(payload["call"]["mediaStats"]["video"]) == 12
    assert {row["stream_index"] for row in videoRows(payload)} == set(range(12))


def test_the_first_fixture_is_unchanged():
    """The payload the other tests were written on still maps as it did."""
    rows = videoRows(load("payload.json"))
    assert {(r["stream_index"], r["direction"]) for r in rows} == {(0, "tx"), (0, "rx"), (1, "tx"), (1, "rx")}


# ------------------------------------------------------------- recent payload

def test_peer_codecs_direction_and_versions_are_read():
    row = callRow(load("payload_media.json"))
    assert row["peer_user_agent"].startswith("TANDBERG/529")
    assert row["peer_user_agent"].endswith("Cisco-RoomKitMini")
    assert row["audio_codec"] == "opus"
    assert row["video_codec"] == "H264"
    assert row["video_encoder"].startswith("H264")
    assert row["media_direction"]["video"] == "sendrecv"
    assert row["gw_version"] == "v1.8.9-71-gb06bc8f"
    assert row["baresip_version"] == "3.15.0"
    assert row["baresip_patch"] == "v3.15.0_patchv5"
    assert row["chromium_version"].startswith("153.")


def test_the_sample_summary_of_a_normal_call():
    row = callRow(load("payload_media.json"))
    assert row["video_state"] == "ok"
    assert row["video_min_rx_fps"] > 20
    assert row["video_low_intervals"] == 0
    assert row["video_keyframe_requests"] == 34
    assert row["presentation_s"] == 0, "the 2x2 placeholder on the slides channel is not a presentation"


def test_video_repeated_by_101_is_reduced_to_the_last_pair():
    """3 samples, 8 entries (2n + 2): only the pair written at hang-up is kept,
    numbered 0 (main) and 1 (slides), with its cumulative end values."""
    payload = load("payload_media.json")
    video = payload["call"]["mediaStats"]["video"]
    assert len(video) == 2 * len(payload["call"]["mediaStats"]["samples"]) + 2
    rows = videoRows(payload)
    assert {(r["stream_index"], r["direction"]) for r in rows} == {(0, "tx"), (0, "rx"), (1, "tx"), (1, "rx")}
    mainRx = next(r for r in rows if r["stream_index"] == 0 and r["direction"] == "rx")
    assert mainRx["packets"] == video[-2]["rx"]["packets"]
    assert mainRx["packets"] == max(v["rx"]["packets"] for v in video[0::2])


def test_a_presentation_is_measured_and_its_call_reduced():
    payload = load("payload_presentation.json")
    row = callRow(payload)
    assert 120 <= row["presentation_s"] <= 140      # 142 s to 274 s, sampled every ~10 s
    assert row["video_state"] == "ok"
    assert len(payload["call"]["mediaStats"]["video"]) == 92
    assert len(videoRows(payload)) == 4


def test_a_fixed_gateway_payload_is_left_as_is():
    """Once logParse is fixed: two entries whatever the number of samples."""
    payload = copy.deepcopy(load("payload_media.json"))
    stats = payload["call"]["mediaStats"]
    stats["video"] = stats["video"][-2:]
    assert len(videoRows(payload)) == 4


def test_two_real_streams_without_samples_are_kept():
    """Before #101, 4 entries could be streams that came and went."""
    stats = {"video": [{"rx": {"packets": 10}}, {"rx": {"packets": 0}},
                       {"rx": {"packets": 5}}, {"rx": {"packets": 0}}]}
    assert {r["stream_index"] for r in mediaRows(stats)} == {0, 1, 2, 3}


# ----------------------------------------------------------- partial pushes

def test_a_call_that_never_came_up_maps_without_a_start():
    row = callRow(load("payload_not_established.json"))
    assert row["call_id"] == "02b19e9c45563f83ce6ead373411bb0b"
    assert row["call_start"] is None               # the trigger dates it
    assert row["media_direction"] is None          # {} says nothing
    assert row["audio_codec"] is None and row["video_state"] is None
    assert row["gw_version"] == "v1.8.9-71-gb06bc8f"


def test_an_empty_push_has_no_call_id():
    """The route refuses it on that ground; the mapping just reports it."""
    assert callRow(load("payload_empty.json"))["call_id"] is None


# --------------------------------------------------------- synthetic samples

def sample(seconds, frames, picup=0, slides=None):
    return {"seconds": seconds,
            "video": {"main": {"rxFrames": frames, "rxPicup": picup},
                      "slides": slides or {"source": "fakevideo", "rxFrames": 0}}}


def test_a_frozen_picture_is_stalled():
    samples = [sample(10, 300), sample(20, 600), sample(30, 610), sample(40, 900, picup=7)]
    summary = sampleSummary(samples, {"video": "sendrecv"})
    assert summary["video_state"] == "stalled"
    assert summary["video_low_intervals"] == 1
    assert summary["video_min_rx_fps"] == 1.0
    assert summary["video_keyframe_requests"] == 7


def test_one_way_video_comes_from_the_media_direction():
    """A one-way picture receives nothing: it is one-way, not frozen."""
    for direction in ("sendonly", "recvonly"):
        summary = sampleSummary([sample(10, 0), sample(20, 0)], {"video": direction})
        assert summary["video_state"] == "oneway"


def test_rates_use_the_wall_clock_seconds_of_each_sample():
    summary = sampleSummary([sample(10, 0), sample(15, 150)])
    assert summary["video_min_rx_fps"] == 30.0


def test_a_room_sharing_is_a_presentation_too():
    slides = [{"source": "fakevideo", "rxFrames": 0}, {"source": "fakevideo", "rxFrames": 50},
              {"source": "fakevideo", "rxFrames": 100}]
    samples = [sample(10 * (i + 1), 300 * (i + 1), slides=s) for i, s in enumerate(slides)]
    assert sampleSummary(samples)["presentation_s"] == 20


def test_missing_keys_and_odd_samples_are_tolerated():
    samples = [{"seconds": 10, "video": {"main": {}}}, {"seconds": 20}, "x",
               {"seconds": 20, "video": {"main": {"rxFrames": 5}}}]
    summary = sampleSummary(samples)
    assert summary["video_min_rx_fps"] is None
    assert sampleSummary(None)["video_state"] is None
    assert mediaDetails({"call": {}})["video_state"] is None


def test_the_threshold_is_five_frames_per_second():
    assert LOW_FPS == 5.0


# ------------------------------------------------ the backfill's shape test

def test_repeated_readings_are_recognised_without_samples():
    """The 15/09 call: counters never decrease from one pair to the next."""
    assert looksCumulative(load("payload_before_media.json")["call"]["mediaStats"]["video"])


def test_streams_that_restart_are_not_repeats():
    video = [{"rx": {"packets": 500}}, {"rx": {"packets": 0}},
             {"rx": {"packets": 20}}, {"rx": {"packets": 0}}]
    assert not looksCumulative(video)
    assert not looksCumulative(video[:2])          # a single pair is just a call
    assert not looksCumulative(video[:3])          # odd: not pairs


# ------------------------------------------------------------- P16 refinements

def test_nothing_measured_is_unknown_even_when_both_ways():
    """Call 3263: one sample, no rate. sendrecv says what was negotiated, not
    what arrived: the state is unknown, not ok."""
    summary = sampleSummary([sample(10, 300)], {"video": "sendrecv"})
    assert summary["video_state"] is None
    assert summary["video_min_rx_fps"] is None


def test_no_picture_at_all_is_not_a_stall():
    """Call 3192: 3 frames, then nothing for the whole call. Maybe a camera
    turned off: said as such, not as a picture that dropped."""
    summary = sampleSummary([sample(10, 3), sample(21, 3)], {"video": "sendrecv"})
    assert summary["video_state"] == "no_picture"


def test_a_picture_that_stops_before_the_end_is_a_stall():
    """Call 3197: 29 frames/s for seven minutes, then frozen for the last 45 s."""
    frames = [294, 619, 942, 1265, 1583, 1583, 1583]
    summary = sampleSummary([sample(10 + 11 * i, f) for i, f in enumerate(frames)], {"video": "sendrecv"})
    assert summary["video_state"] == "stalled"
    assert summary["video_low_intervals"] == 2


def test_a_repeat_missing_from_samples_is_still_a_repeat():
    """Call 3254: 4 entries, samples empty, counters rising: a sample reached
    the log without reaching `samples`. Only the last pair is kept."""
    video = [{"rx": {"packets": 100}}, {"rx": {"packets": 0}},
             {"rx": {"packets": 250}}, {"rx": {"packets": 0}}]
    stats = {"video": video, "samples": []}
    assert isRepeated(stats)
    rows = mediaRows(stats)
    assert {(r["stream_index"], r["packets"]) for r in rows} == {(0, 250), (1, 0)}


def test_real_streams_after_the_fix_are_kept():
    """Once logParse is fixed, 4 entries that restart are streams again."""
    video = [{"rx": {"packets": 500}}, {"rx": {"packets": 0}},
             {"rx": {"packets": 20}}, {"rx": {"packets": 0}}]
    stats = {"video": video, "samples": [{"seconds": 10}, {"seconds": 20}, {"seconds": 30}]}
    assert not isRepeated(stats)
    assert {r["stream_index"] for r in mediaRows(stats)} == {0, 1, 2, 3}


def test_frame_rates_for_the_drawer_chart():
    rates = frameRates(load("payload_presentation.json")["call"]["mediaStats"]["samples"])
    assert len(rates) == 44
    assert all(set(r) == {"t", "seconds", "rx", "tx", "presentation"} for r in rates)
    assert rates[0]["rx"] > 20 and rates[0]["presentation"] is False
    shown = [r["t"] for r in rates if r["presentation"]]
    assert 140 <= min(shown) <= 160 and 260 <= max(shown) <= 290
    assert frameRates(None) == [] and frameRates([sample(10, 1)]) == []
