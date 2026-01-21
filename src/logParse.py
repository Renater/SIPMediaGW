#!/usr/bin/env python3
from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse, urlsplit

import requests


### Config ###

POST_URL = os.environ.get("LOG_PUSH_URL", "").strip()

### Regex ###

ANSI_ESCAPE_REGEX = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

BARESIP_REGEX = re.compile(r"^sip:(?P<dest_user>[^@]+)@(?P<dest_dom>[^:]+):\s*Call with\s*sip:(?P<src_user>[^@]+)@(?P<src_dom>\S+)")

DTMF_REGEX = re.compile(r"^(?:Event:\s*)?Received DTMF:(?P<input>.+)$")

STAT_HEADER_REGEX = re.compile(r"^(?P<media>audio|video)(?:\s+(?P<stream>\d+))?\s+Transmit:\s*Receive:\s*$")

STAT_VALUE_REGEX = re.compile(r"^(?P<label>[^:]+):\s*(?P<rest>.+)$")

NUM_REGEX = re.compile(r"[-+]?\d+(?:\.\d+)?")

FIELD_MAP = {
    "packets": "packets",
    "errors": "errors",
    "pkt.report": "packetReports",
    "avg. bitrate": "avgBitrateKbps",
    "lost": "lostPackets",
    "jitter": "jitterMs",
}


### Time functions ###

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def iso_z(dt: datetime, *, ms: bool = False) -> str:
    s = dt.astimezone(timezone.utc).isoformat(timespec="milliseconds" if ms else "seconds")
    return s.replace("+00:00", "Z")

def raw_timestamp(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%b %d %H:%M:%S")

def parse_iso(timestamp: str) -> Optional[datetime]:
    if not timestamp:
        return None
    try:
        if timestamp.endswith("Z"):
            return datetime.fromisoformat(timestamp[:-1]).replace(tzinfo=timezone.utc)
        dt = datetime.fromisoformat(timestamp)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None

def to_number(s: str) -> int | float:
    return float(s) if "." in s else int(s)


### SIP functions ###

### Add sip: prefix to parse it better later ###

def normalize_sip_uri(uri: str) -> str:
    clean_uri = (uri or "").strip()
    if not clean_uri:
        return ""
    if clean_uri.startswith("sip:"):
        return clean_uri
    if "@" in clean_uri:
        return "sip:" + clean_uri
    return clean_uri

### Remove sip: prefix ###
def strip_sip_prefix(uri: str) -> str:
    clean_uri = (uri or "").strip()
    return clean_uri[4:] if clean_uri.startswith("sip:") else clean_uri


### Split prefix ### 
def split_uri(uri: str) -> Tuple[str, str]:
    clean_uri = strip_sip_prefix(uri)
    if "@" not in clean_uri:
        return "", ""
    user, dom = clean_uri.split("@", 1)
    return user, dom

### Get displayName & mixedId from URL ###

def parse_call_url_details(url: str) -> dict[str, str]:
    url = (url or "").strip()
    if not url:
        return {}

    parts = urlsplit(url)
    params = parse_qs(parts.query or "", keep_blank_values=True)

    source_name = (params.get("displayName", [""])[0] or "").strip()
    destination_room_name = (params.get("mixedId", [""])[0] or "").strip()

    details: dict[str, str] = {}
    if source_name:
        details["sourceName"] = source_name
    if destination_room_name:
        details["destinationRoomName"] = destination_room_name
    return details

### Parse Event logs ###

def parse_event_dict(line: str) -> Optional[Dict[str, Any]]:
    text = (line or "").strip()
    if text.startswith("Event:"):
        text = text.split("Event:", 1)[1].strip()

    if not (text.startswith("{") and text.endswith("}")):
        return None
    if "'type'" not in text and '"type"' not in text:
        return None

    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except Exception:
        pass

    try:
        obj = ast.literal_eval(text)
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


### Add to history file ###

def append_history(history_path: str, record_type: str, record_obj: Dict[str, Any]) -> None:

    if not history_path:
        return

    line = f"{record_type}:{json.dumps(record_obj, ensure_ascii=False)}\n"

    try:
        import fcntl

        with open(history_path, "a", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.write(line)
            f.flush()
            fcntl.flock(f, fcntl.LOCK_UN)
    except Exception as exc:
        print("Failed to write history:", exc, file=sys.stderr, flush=True)


def read_history_stable(history_path: str, *, max_wait_s: float = 5.0) -> List[str]:

    if not history_path:
        return []

    try:
        import fcntl

        previous_sig: Optional[Tuple[int, str]] = None
        stable_count = 0

        deadline = time.time() + max_wait_s
        while time.time() < deadline:
            with open(history_path, "a+", encoding="utf-8") as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                f.seek(0)
                lines = f.readlines()
                sig = (len(lines), lines[-1] if lines else "")
                fcntl.flock(f, fcntl.LOCK_UN)

            if sig == previous_sig:
                stable_count += 1
            else:
                stable_count = 0
            previous_sig = sig

            if stable_count >= 2:
                return lines

            time.sleep(0.2)

        return lines

    except Exception:
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                return f.readlines()
        except Exception:
            return []


def truncate_history(history_path: str) -> None:
    if not history_path:
        return
    try:
        import fcntl

        with open(history_path, "a+", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.seek(0)
            f.truncate(0)
            fcntl.flock(f, fcntl.LOCK_UN)
    except Exception as exc:
        print("Failed to truncate history:", exc, file=sys.stderr, flush=True)


### Payload ###

@dataclass
class MediaStats:
    audio_tx: Dict[str, Any] = field(default_factory=dict)
    audio_rx: Dict[str, Any] = field(default_factory=dict)
    video_streams: Dict[int, Dict[str, Any]] = field(default_factory=dict)


def build_payload_from_lines(lines: List[str], post_url: str) -> Dict[str, Any]:

    room_type = "IVR"
    main_app = ""

    call_start_raw = ""
    call_start_timestamp = ""
    call_end_raw = ""
    call_end_timestamp = ""
    call_url = ""

    call_id = ""
    peer_display = ""
    close_reason = ""
    last_event_type = ""


    source_uri = ""
    destination_uri = ""
    destination_domain = ""
    destination_uri_raw = ""

    room_line_value = ""
    source_name = ""
    dtmf_events: List[Dict[str, str]] = []
    media = MediaStats()

    have_final_call_closed = False

    for history_line in lines:
        history_line = history_line.strip()
        if not history_line or ":" not in history_line:
            continue

        record_type, record_payload = history_line.split(":", 1)
        record_type = record_type.strip()

        if record_type == "main_app":
            main_app = (record_payload or "").strip()
            continue

        try:
            record_data = json.loads(record_payload)
        except Exception:
            continue

        if record_type == "call_start":
            call_start_raw = call_start_raw or (record_data.get("raw") or "")
            call_start_timestamp = call_start_timestamp or (record_data.get("timestamp") or "")
            if record_data.get("url"):
                call_url = record_data.get("url") or ""

        elif record_type == "call_end":
            if record_data.get("raw"):
                call_end_raw = record_data.get("raw") or ""
            if record_data.get("timestamp"):
                call_end_timestamp = record_data.get("timestamp") or ""

        elif record_type == "room":
            room_line_value = (record_data.get("value") or "").strip()

        elif record_type == "destination":
            if record_data.get("destinationURI"):
                destination_uri = (record_data.get("destinationURI") or "").strip()
            if record_data.get("destinationDomain"):
                destination_domain = (record_data.get("destinationDomain") or "").strip()

        elif record_type == "call_closed":
            event_type = (record_data.get("lastEventType") or "").strip()
            is_final = event_type == "CALL_CLOSED"

            if have_final_call_closed and not is_final:
                continue
            if is_final:
                have_final_call_closed = True

            call_id = record_data.get("callId") or call_id
            peer_display = (record_data.get("peerDisplayName") or peer_display).strip()
            close_reason = record_data.get("closeReason") or close_reason
            last_event_type = event_type or last_event_type

            if record_data.get("sourceURI"):
                source_uri = normalize_sip_uri(record_data["sourceURI"])
            if record_data.get("destinationURI"):
                destination_uri_raw = normalize_sip_uri(record_data["destinationURI"])

        elif record_type == "dtmf":
            ts = record_data.get("timestamp") or ""
            inp = (record_data.get("input") or "").strip()
            if ts and inp:
                dtmf_events.append({"timestamp": ts, "input": inp})

        elif record_type == "stats_value":
            media_type = (record_data.get("media") or "").strip().lower()
            field = (record_data.get("field") or "").strip()
            tx = record_data.get("tx")
            rx = record_data.get("rx")
            if not media_type or not field:
                continue

            if media_type == "audio":
                if tx is not None:
                    media.audio_tx[field] = tx
                if rx is not None:
                    media.audio_rx[field] = rx

            elif media_type == "video":
                stream_idx_val = record_data.get("streamIndex")
                try:
                    stream_idx = int(stream_idx_val) if stream_idx_val is not None else 0
                except Exception:
                    stream_idx = 0

                stream_stats = media.video_streams.setdefault(
                    stream_idx, {"streamIndex": stream_idx, "tx": {}, "rx": {}}
                )
                if tx is not None:
                    stream_stats["tx"][field] = tx
                if rx is not None:
                    stream_stats["rx"][field] = rx

    ### Get sourceName & destinationRoomName from URL ###
    url_details = parse_call_url_details(call_url)
    if url_details.get("sourceName"):
        source_name = url_details["sourceName"]
    if url_details.get("destinationRoomName"):
        destination_room_name = url_details["destinationRoomName"]

    source_uri = normalize_sip_uri(source_uri)

    ### Destination RAW data ###
    raw_aor = strip_sip_prefix(destination_uri_raw)
    raw_dest_alias, raw_dest_alias_domain = split_uri(destination_uri_raw)
    destination_domain_ip = raw_dest_alias_domain or ""
    destination_gw = raw_dest_alias or ""

    ### Remove sip: prefix ###
    destination_uri = strip_sip_prefix(destination_uri)
    source_number, source_domain = split_uri(source_uri)

    ### Duration ###
    total_seconds = 0
    total_ms = 0
    total_raw = "00:00:00"

    start_date = parse_iso(call_start_timestamp)
    end_date = parse_iso(call_end_timestamp)
    if start_date and end_date and end_date >= start_date:
        dur = end_date - start_date
        sec = int(dur.total_seconds())
        total_seconds = sec
        total_ms = sec * 1000
        total_raw = f"{sec // 3600:02d}:{(sec % 3600) // 60:02d}:{sec % 60:02d}"

    media_stats = {
        "audio": {"tx": media.audio_tx, "rx": media.audio_rx},
        "video": [media.video_streams[i] for i in sorted(media.video_streams)] if media.video_streams else [],
    }

    call_obj = {
        "roomType": room_type,
        "mainApp": main_app,
        "callSession": {
            "callStart": {"raw": call_start_raw, "timestamp": call_start_timestamp},
            "callEnd": {"raw": call_end_raw, "timestamp": call_end_timestamp},
            "totalTime": {"seconds": total_seconds, "milliseconds": total_ms, "raw": total_raw},
        },
        "details": {
            "callId": call_id,
            "source": {
                "sourceURI": strip_sip_prefix(source_uri),
                "sourceName": source_name,
                "sourceNumber": source_number,
                "sourceDomain": source_domain,
            },
            "destination": {
                "destinationURI": destination_uri,
                "destinationRoomName": destination_room_name,
                "destinationDomain": destination_domain,

                "destinationDomainRaw": raw_aor,
                "destinationGw": destination_gw,
                "destinationDomainIp": destination_domain_ip,
                "peerDisplayName": peer_display,
            },
            "closeReason": close_reason,
            "lastEventType": last_event_type,
        },
        "dtmfEvents": dtmf_events,
        "mediaStats": media_stats,
    }

    json_body = {"call": call_obj}
    return json_body


### Post ###
def push_history(history_path: str) -> None:

    if not history_path or not POST_URL:
        return

    try:
        lines = read_history_stable(history_path, max_wait_s=5.0)
        if not lines:
            return

        payload = build_payload_from_lines(lines, POST_URL)
        resp = requests.post(
            POST_URL,
            json=payload,
            headers={"Accept": "text/plain"},
            timeout=10,
        )

        if not (200 <= resp.status_code < 300):
            print(f"POST failed status={resp.status_code} body={resp.text!r}", file=sys.stderr, flush=True)
            return

        truncate_history(history_path)

    except Exception as exc:
        print("Failed to post call history:", exc, file=sys.stderr, flush=True)


### Main ###

def main() -> None:
    parser = argparse.ArgumentParser(description="Log parser")
    parser.add_argument("-p", "--pref", required=True, help="log prefix (e.g. Event, Baresip)")
    parser.add_argument("-i", "--history", required=False, help="history file path")
    args = parser.parse_args()

    pref: str = args.pref
    history_file: str = args.history or ""

    current_media: Optional[str] = None
    current_stream: Optional[int] = None
    video_auto_index = -1
    last_final_call_id: Optional[str] = None

    for raw_input_line in sys.stdin:
        line = ANSI_ESCAPE_REGEX.sub("", raw_input_line.rstrip())
        if not line:
            continue

        print(f"{pref}: {line}", flush=True)

        if not history_file:
            continue

        try:
            ### Call start ###
            if "Web browsing URL:" in line:
                dt = utc_now()
                url = ""
                if "URL:" in line:
                    url = line.split("URL:", 1)[1].strip()
                append_history(
                    history_file,
                    "call_start",
                    {"raw": raw_timestamp(dt), "timestamp": iso_z(dt), "url": url},
                )
                continue

            ### Room ###
            if "room:" in line:
                append_history(history_file, "room", {"value": line.split("room:", 1)[1].strip()})
                continue

            ### Event ###
            if pref == "Event":
                dtmf_match = DTMF_REGEX.match(line.strip())
                if dtmf_match:
                    dt = utc_now()
                    append_history(
                        history_file,
                        "dtmf",
                        {"timestamp": iso_z(dt, ms=True), "input": dtmf_match.group("input").strip()},
                    )
                    continue

                event_dict = parse_event_dict(line)
                if event_dict and event_dict.get("class") == "call":
                    last_type = str(event_dict.get("type") or "").strip()
                    if last_type != "CALL_CLOSED":
                        continue

                    call_id = str(event_dict.get("id") or "").strip()
                    if call_id and call_id == last_final_call_id:
                        continue
                    if call_id:
                        last_final_call_id = call_id

                    peeruri = str(event_dict.get("peeruri") or "").strip()
                    accountaor = str(event_dict.get("accountaor") or "").strip()
                    peerdisplay = str(event_dict.get("peerdisplayname") or "").strip()
                    close_reason = str(event_dict.get("param") or "").strip()

                    append_history(
                        history_file,
                        "call_closed",
                        {
                            "callId": call_id,
                            "peerDisplayName": peerdisplay,
                            "closeReason": close_reason,
                            "lastEventType": last_type,
                            "sourceURI": normalize_sip_uri(peeruri),
                            "destinationURI": normalize_sip_uri(accountaor),
                        },
                    )

                    dt = utc_now()
                    append_history(history_file, "call_end", {"raw": raw_timestamp(dt), "timestamp": iso_z(dt)})

                    push_history(history_file)
                    continue

            ### Baresip ###
            if pref == "Baresip":
                call_line_match = BARESIP_REGEX.match(line.strip())
                if call_line_match:
                    dest_user = call_line_match.group("dest_user")
                    dest_dom = call_line_match.group("dest_dom")
                    append_history(
                        history_file,
                        "destination",
                        {
                            "destinationURI": f"{dest_user}@{dest_dom}",
                            "destinationRoomName": dest_user,
                            "destinationDomain": dest_dom,
                        },
                    )
                    continue

                ### QOS ###
                stats_header_match = STAT_HEADER_REGEX.match(line.strip())
                if stats_header_match:
                    current_media = stats_header_match.group("media").strip().lower()
                    if current_media == "video":
                        stream_s = stats_header_match.group("stream")
                        if stream_s is not None:
                            current_stream = int(stream_s)
                            video_auto_index = max(video_auto_index, current_stream)
                        else:
                            video_auto_index += 1
                            current_stream = video_auto_index
                    else:
                        current_stream = None
                    continue

                ### QOS values ###
                stats_value_match = STAT_VALUE_REGEX.match(line.strip())
                if stats_value_match and current_media in ("audio", "video"):
                    label = stats_value_match.group("label").strip()
                    if label in FIELD_MAP:
                        nums = NUM_REGEX.findall(stats_value_match.group("rest"))
                        tx = to_number(nums[0]) if len(nums) >= 1 else None
                        rx = to_number(nums[1]) if len(nums) >= 2 else None
                        append_history(
                            history_file,
                            "stats_value",
                            {
                                "media": current_media,
                                "streamIndex": current_stream,
                                "field": FIELD_MAP[label],
                                "tx": tx,
                                "rx": rx,
                            },
                        )
                    continue

                ### Baresip end ###
                if (
                    "ua: stop all" in line
                    or "Files sent and removed" in line
                    or "Files moved in log directory" in line
                ):
                    dt = utc_now()
                    append_history(history_file, "call_end", {"raw": raw_timestamp(dt), "timestamp": iso_z(dt)})
                    push_history(history_file)
                    continue

        except Exception as exc:
            print("Failed to parse log line:", exc, file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
