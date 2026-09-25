"""
Map a logParse.py call-history payload to database rows.

Kept free of any database dependency so it can be unit-tested against real
payloads captured from a gateway. The previous collector built the video
statistics and then dropped them; here the mapping is covered by tests.

The payload's shape follows SIPMediaGW's pull requests, cited by number:
  #99   the proxyAPI derives each gateway's state (read by proxyapi.py);
  #101  periodic media samples (mediaStats.samples) — its first version also
        repeated the video summary once per sample, which is cleaned here;
  #102  peer, encoders and media direction;
  #105  gateway, baresip and Chromium versions.
"""

import math
from datetime import datetime, timezone


def _text(value):
    """Empty strings are not identifiers: store them as NULL."""
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _ts(value):
    """Parse an ISO 8601 timestamp; the gateway sends UTC with a 'Z' suffix."""
    value = _text(value)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


# The widest value an INTEGER column holds. A counter or a duration beyond it
# is not a measurement (1e20 seconds), and PostgreSQL would refuse the whole
# call with it: it is read as missing instead, like any other unusable value.
INT_LIMIT = 2**31 - 1


def _int(value):
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError):     # OverflowError: int(float('inf'))
        return None
    return number if -INT_LIMIT <= number <= INT_LIMIT else None


def _float(value):
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _obj(value):
    """A JSON object, or an empty one: a list or a string where an object is
    expected is a malformed block, read as absent rather than failing the push."""
    return value if isinstance(value, dict) else {}


def _streamRows(block, media, streamIndex):
    """One row per direction (tx/rx) of a single stream."""
    rows = []
    for direction in ("tx", "rx"):
        stats = _obj(block).get(direction)
        if not isinstance(stats, dict):
            continue
        rows.append({
            "media": media,
            "stream_index": streamIndex,
            "direction": direction,
            "packets": _int(stats.get("packets")),
            "errors": _int(stats.get("errors")),
            "packet_reports": _int(stats.get("packetReports")),
            "avg_bitrate_kbps": _float(stats.get("avgBitrateKbps")),
            "lost_packets": _int(stats.get("lostPackets")),
            "jitter_ms": _float(stats.get("jitterMs")),
        })
    return rows


def isRepeated(mediaStats):
    """True when mediaStats.video holds #101 repeats rather than streams."""
    video = mediaStats.get("video")
    if isinstance(video, dict):
        return False
    video = [stream for stream in (video or []) if isinstance(stream, dict)]
    samples = mediaStats.get("samples")
    if not isinstance(samples, list) or len(video) < 4:
        return False
    return (bool(samples) and len(video) >= 2 * len(samples)) or looksCumulative(video)


def _videoEntries(mediaStats):
    """
    The video streams worth storing.

    From SIPMediaGW #101 until its fix, every periodic media sample also made
    logParse append a statistics block to mediaStats.video: a call with n
    samples carries 2n + 2 cumulative entries (main, slides, again and
    again), not 2n + 2 streams. The signature is that count, so the rule
    keys on it and switches itself off on fixed payloads (two entries for n
    samples). Only the last pair is kept, the one written at hang-up, and it
    is renumbered 0 (main) and 1 (slides). Payloads without samples keep
    every entry: before #101, several entries were real streams.

    A sample may reach the log without reaching `samples` (a 10-second call
    with 4 entries and no sample, seen on the lab): once the payload has the
    samples key, entries whose counters never decrease from one pair to the
    next are repeats too, whatever the count.
    """
    video = mediaStats.get("video")
    if isinstance(video, dict):          # tolerate a single object
        video = [video]
    video = [stream for stream in (video or []) if isinstance(stream, dict)]
    if isRepeated(mediaStats):
        last = video[-2:]
        return [(position, stream) for position, stream in enumerate(last)]
    return [(position if _int(stream.get("streamIndex")) is None else _int(stream.get("streamIndex")), stream)
            for position, stream in enumerate(video)]


def looksCumulative(video):
    """
    True when a video list without samples still has the #101 shape: an even
    number of entries, at least two pairs, and every counter of the main
    entries (even positions) and of the slides entries (odd positions) never
    decreasing from one pair to the next. Separate streams restart at zero;
    repeated readings of the same stream do not.

    Only the backfill uses it, for the calls pushed on 15/09 by the branch
    that became #101, before samples were in the payload. Live pushes rely on
    the samples count, which says it without guessing.
    """
    video = [stream for stream in (video or []) if isinstance(stream, dict)]
    if len(video) < 4 or len(video) % 2:
        return False

    def counters(stream):
        return [_int(_obj(stream.get(direction)).get(key)) or 0
                for direction in ("rx", "tx") for key in ("packets", "packetReports")]

    for start in (0, 1):
        series = [counters(stream) for stream in video[start::2]]
        for before, after in zip(series, series[1:]):
            if any(b < a for a, b in zip(before, after)):
                return False
    return True


def mediaRows(mediaStats):
    """
    Flatten mediaStats into rows.

    audio is a single object; video a list of streams (index 0 the camera,
    index 1 the presentation channel), cleaned of the #101 duplicates.
    """
    mediaStats = _obj(mediaStats)
    rows = []
    rows.extend(_streamRows(mediaStats.get("audio"), "audio", 0))
    for index, stream in _videoEntries(mediaStats):
        rows.extend(_streamRows(stream, "video", index))
    return rows


# ------------------------------------------------------------ media details

# Video states: see sampleSummary().
# Below this many frames per second received on the main stream, over one
# sampling interval, the picture is counted as interrupted.
LOW_FPS = 5.0
# A slides stream from this source carries nothing: the gateway keeps a 2x2
# placeholder on the channel so that some endpoints keep the BFCP session.
PLACEHOLDER_SOURCE = "fakevideo"


def _codec(line):
    """'H264 packetization-mode=0 (…)' -> 'H264'; 'opus 48000Hz 2ch' -> 'opus'."""
    text = _text(line)
    return text.split()[0] if text else None


def _direction(value):
    """mediaDir as given, or None when it says nothing (an unanswered call sends {})."""
    if not isinstance(value, dict):
        return None
    cleaned = {key: _text(val) for key, val in value.items() if _text(val)}
    return cleaned or None


def _points(samples):
    return [s for s in (samples or []) if isinstance(s, dict) and isinstance(s.get("video"), dict)]


def _part(sample, name):
    value = sample["video"].get(name)
    return value if isinstance(value, dict) else {}


def frameRates(samples):
    """
    Frames per second over each interval between two samples: received and
    sent on the main picture, and whether a presentation was running. One
    entry per interval, at its end (`t`, wall-clock seconds of the call).

    Counters are cumulative since the start of the stream; the interval is
    measured on the wall-clock `seconds` every sample carries (rxSeconds
    stops with the stream, which is the very case to catch). Missing keys
    are tolerated: a slides sample during a presentation has no txSeconds.
    """
    points = _points(samples)
    rates = []
    for before, after in zip(points, points[1:]):
        seconds = (_float(after.get("seconds")) or 0) - (_float(before.get("seconds")) or 0)
        if seconds <= 0:
            continue
        a, b = _part(before, "main"), _part(after, "main")

        def rate(key):
            start, stop = _int(a.get(key)), _int(b.get(key))
            return None if start is None or stop is None else round((stop - start) / seconds, 1)

        slidesBefore, slidesAfter = _part(before, "slides"), _part(after, "slides")
        sending = (_text(slidesAfter.get("source")) or PLACEHOLDER_SOURCE) != PLACEHOLDER_SOURCE
        receiving = (_int(slidesAfter.get("rxFrames")) or 0) > (_int(slidesBefore.get("rxFrames")) or 0)
        rates.append({"t": _float(after.get("seconds")), "seconds": seconds,
                      "rx": rate("rxFrames"), "tx": rate("txFrames"),
                      "presentation": sending or receiving})
    return rates


def sampleSummary(samples, direction=None):
    """
    What the periodic samples (SIPMediaGW #101) say about the main picture.

    video_state, from the received side:
      oneway      mediaDir says sendonly or recvonly
      no_picture  no interval reached LOW_FPS: nothing came in, which may be
                  a camera the caller turned off, not a fault
      stalled     the picture came in, then at least one interval fell below
      ok          every measured interval at LOW_FPS or above
      None        nothing measured (fewer than two samples): unknown, and
                  not "ok" — a direction alone says nothing of the picture
    """
    result = {"video_min_rx_fps": None, "video_low_intervals": None,
              "video_keyframe_requests": None, "presentation_s": None, "video_state": None}
    if (direction or {}).get("video") in ("sendonly", "recvonly"):
        result["video_state"] = "oneway"

    points = _points(samples)
    if not points:
        return result
    intervals = frameRates(points)
    rates = [entry["rx"] for entry in intervals if entry["rx"] is not None]
    result["video_keyframe_requests"] = _int(_part(points[-1], "main").get("rxPicup"))
    result["presentation_s"] = int(round(sum(e["seconds"] for e in intervals if e["presentation"])))
    if rates:
        low = sum(1 for rate in rates if rate < LOW_FPS)
        result["video_min_rx_fps"] = round(min(rates), 1)
        result["video_low_intervals"] = low
        if result["video_state"] is None:
            result["video_state"] = ("ok" if not low else
                                     "no_picture" if low == len(rates) else "stalled")
    return result


def mediaDetails(payload):
    """
    The #102 and #105 fields and the #101 summary, as `calls` columns. Every
    one of them is absent from calls pushed before those changes, and stays
    None: absent, not wrong.
    """
    call = _obj(payload.get("call"))
    details = _obj(call.get("details"))
    gateway = call.get("gateway") if isinstance(call.get("gateway"), dict) else {}
    encoders = details.get("encoders") if isinstance(details.get("encoders"), dict) else {}
    videoLines = encoders.get("video") if isinstance(encoders.get("video"), list) else []
    direction = _direction(details.get("mediaDir"))
    mediaStats = call.get("mediaStats") if isinstance(call.get("mediaStats"), dict) else {}
    row = {
        "peer_user_agent": _text(details.get("peerUserAgent")),
        "audio_codec": _codec(encoders.get("audio")),
        # The first line is the main picture; the encoder settings are a
        # target (bit rate, frame rate), not a measurement, and are kept as
        # written for the detail view.
        "video_codec": _codec(videoLines[0]) if videoLines else None,
        "video_encoder": _text(videoLines[0]) if videoLines else None,
        "media_direction": direction,
        "gw_version": _text(gateway.get("gwVersion")),
        "baresip_version": _text(gateway.get("baresipVersion")),
        "baresip_patch": _text(gateway.get("baresipPatch")),
        "chromium_version": _text(gateway.get("chromiumVersion")),
    }
    row.update(sampleSummary(mediaStats.get("samples"), direction))
    return row


def callRow(payload):
    """
    Map the payload to the `calls` columns.

    Raises ValueError when the document does not look like a call history,
    so that the route answers 400 instead of inserting an empty row.
    """
    if not isinstance(payload, dict):
        raise ValueError("payload is not an object")
    call = payload.get("call")
    if not isinstance(call, dict):
        raise ValueError("missing 'call' object")

    session = _obj(call.get("callSession"))
    details = _obj(call.get("details"))
    source = _obj(details.get("source"))
    destination = _obj(details.get("destination"))
    total = _obj(session.get("totalTime"))

    seconds = _int(total.get("seconds"))
    if seconds is None:
        milliseconds = _int(total.get("milliseconds"))
        seconds = milliseconds // 1000 if milliseconds is not None else None

    return {
        "call_id": _text(details.get("callId")),
        "gw_alias": _text(destination.get("destinationGw")),
        # Not sent by logParse yet; kept for the upcoming upstream change.
        "gw_id": _text(call.get("gwId")),
        "gw_host": _text(destination.get("destinationDomainIp")),

        "main_app": _text(call.get("mainApp")),
        "platform": _text(call.get("browsing")),
        "room": _text(call.get("room")),
        "call_url": _text(call.get("callUrl")),

        "source_uri": _text(source.get("sourceURI")),
        "source_name": _text(source.get("sourceName")),
        "source_number": _text(source.get("sourceNumber")),
        "source_domain": _text(source.get("sourceDomain")),
        "destination_uri": _text(destination.get("destinationURI")),
        "destination_room": _text(destination.get("destinationRoomName")),
        "destination_domain": _text(destination.get("destinationDomain")),
        "peer_display_name": _text(destination.get("peerDisplayName")),

        "call_start": _ts(_obj(session.get("callStart")).get("timestamp")),
        "call_end": _ts(_obj(session.get("callEnd")).get("timestamp")),
        "duration_s": seconds,
        "occupancy_s": seconds,
        "close_reason": _text(details.get("closeReason")),
        "last_event_type": _text(details.get("lastEventType")),

        "dtmf_events": call.get("dtmfEvents") or [],
        **mediaDetails(payload),
    }
