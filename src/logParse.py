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
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse, urlsplit

import requests


### Config ###

postUrl = os.environ.get("LOG_PUSH_URL", "").strip()
# Optional shared secret expected by the receiver.
# If unset: the push carries no Authorization header.
postToken = os.environ.get("LOG_PUSH_TOKEN", "").strip()

### Regex ###

ansiEscapeRegex = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")

baresipRegex = re.compile(r"^sip:(?P<dest_user>[^@]+)@(?P<dest_dom>[^:]+):\s*Call with\s*sip:(?P<src_user>[^@]+)@(?P<src_dom>\S+)")

dtmfRegex = re.compile(r"^(?:Event:\s*)?Received DTMF:(?P<input>.+)$")

statHeaderRegex = re.compile(r"^(?P<media>audio|video)(?:\s+(?P<stream>\d+))?\s+Transmit:\s*Receive:\s*$")

statValueRegex = re.compile(r"^(?P<label>[^:]+):\s*(?P<rest>.+)$")

numRegex = re.compile(r"[-+]?\d+(?:\.\d+)?")

fieldMap = {
    "packets": "packets",
    "errors": "errors",
    "pkt.report": "packetReports",
    "avg. bitrate": "avgBitrateKbps",
    "lost": "lostPackets",
    "jitter": "jitterMs",
}


### Time functions ###

def utcNow() -> datetime:
    return datetime.now(timezone.utc)

def isoZ(dt: datetime, *, ms: bool = False) -> str:
    s = dt.astimezone(timezone.utc).isoformat(timespec="milliseconds" if ms else "seconds")
    return s.replace("+00:00", "Z")

def rawTimestamp(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%b %d %H:%M:%S")

# "Set audio encoder: opus 48000Hz 2ch"
# "Set video encoder: H264 packetization-mode=0 (2000000 bit/s, 30.00 fps)"
encoderRegex = re.compile(
    r"Set (?P<media>audio|video) encoder:\s*(?P<rest>.+)$")


def gatewayVersions() -> Dict[str, str]:
    """
    What this gateway is, for the call history.

    Three values are fixed at build time and read from the environment; the
    fourth is read from the image, because the Chromium build falls back to
    whatever the Debian pool still carries and only the file it writes knows
    what was installed.

    A missing value yields "unknown" rather than raising: a payload has to leave
    even when an environment field is absent.
    """
    chromium = "unknown"
    try:
        chromium = Path("/etc/chromium.version").read_text().strip() or "unknown"
    except OSError:
        # Images built before the Chromium fallback have no such file.
        pass
    return {
        "gwVersion": os.environ.get("GW_VERSION", "unknown"),
        "baresipVersion": os.environ.get("BARESIP_VERSION", "unknown"),
        "baresipPatch": os.environ.get("BARESIP_BRANCH", "unknown"),
        "chromiumVersion": chromium,
    }


def parseIso(timestamp: str) -> Optional[datetime]:
    if not timestamp:
        return None
    try:
        if timestamp.endswith("Z"):
            return datetime.fromisoformat(timestamp[:-1]).replace(tzinfo=timezone.utc)
        dt = datetime.fromisoformat(timestamp)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return None

def toNumber(s: str) -> int | float:
    return float(s) if "." in s else int(s)


### SIP functions ###

### Add sip: prefix to parse it better later ###

def normalizeSipUri(uri: str) -> str:
    cleanUri = (uri or "").strip()
    if not cleanUri:
        return ""
    if cleanUri.startswith("sip:"):
        return cleanUri
    if "@" in cleanUri:
        return "sip:" + cleanUri
    return cleanUri

### Remove sip: prefix ###
def stripSipPrefix(uri: str) -> str:
    cleanUri = (uri or "").strip()
    return cleanUri[4:] if cleanUri.startswith("sip:") else cleanUri


### Split prefix ###
def splitUri(uri: str) -> Tuple[str, str]:
    cleanUri = stripSipPrefix(uri)
    if "@" not in cleanUri:
        return "", ""
    user, dom = cleanUri.split("@", 1)
    return user, dom

### Get displayName & mixedId from URL ###

def parseCallUrlDetails(url: str) -> dict[str, str]:
    url = (url or "").strip()
    if not url:
        return {}

    parts = urlsplit(url)
    params = parse_qs(parts.query or "", keep_blank_values=True)

    sourceName = (params.get("displayName", [""])[0] or "").strip()
    destinationRoomName = (params.get("mixedId", [""])[0] or "").strip()

    details: dict[str, str] = {}
    if sourceName:
        details["sourceName"] = sourceName
    if destinationRoomName:
        details["destinationRoomName"] = destinationRoomName
    return details

### Parse Event logs ###

def parseEventDict(line: str) -> Optional[Dict[str, Any]]:
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

def appendHistory(historyPath: str, recordType: str, recordObj: Dict[str, Any]) -> None:

    if not historyPath:
        return

    line = f"{recordType}:{json.dumps(recordObj, ensure_ascii=False)}\n"

    try:
        import fcntl

        with open(historyPath, "a", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.write(line)
            f.flush()
            fcntl.flock(f, fcntl.LOCK_UN)
    except Exception as exc:
        print("Failed to write history:", exc, file=sys.stderr, flush=True)


def readHistoryStable(historyPath: str, *, maxWaitS: float = 5.0) -> List[str]:

    if not historyPath:
        return []

    try:
        import fcntl

        previousSig: Optional[Tuple[int, str]] = None
        stableCount = 0

        deadline = time.time() + maxWaitS
        while time.time() < deadline:
            with open(historyPath, "a+", encoding="utf-8") as f:
                fcntl.flock(f, fcntl.LOCK_EX)
                f.seek(0)
                lines = f.readlines()
                sig = (len(lines), lines[-1] if lines else "")
                fcntl.flock(f, fcntl.LOCK_UN)

            if sig == previousSig:
                stableCount += 1
            else:
                stableCount = 0
            previousSig = sig

            if stableCount >= 2:
                return lines

            time.sleep(0.2)

        return lines

    except Exception:
        try:
            with open(historyPath, "r", encoding="utf-8") as f:
                return f.readlines()
        except Exception:
            return []


def truncateHistory(historyPath: str) -> None:
    if not historyPath:
        return
    try:
        import fcntl

        with open(historyPath, "a+", encoding="utf-8") as f:
            fcntl.flock(f, fcntl.LOCK_EX)
            f.seek(0)
            f.truncate(0)
            fcntl.flock(f, fcntl.LOCK_UN)
    except Exception as exc:
        print("Failed to truncate history:", exc, file=sys.stderr, flush=True)


### Payload ###

@dataclass
class MediaStats:
    audioTx: Dict[str, Any] = field(default_factory=dict)
    audioRx: Dict[str, Any] = field(default_factory=dict)
    videoStreams: Dict[int, Dict[str, Any]] = field(default_factory=dict)


def buildPayloadFromLines(lines: List[str], postUrl: str) -> Dict[str, Any]:

    roomType = "IVR"
    mainApp = ""

    callStartRaw = ""
    callStartTimestamp = ""
    callEndRaw = ""
    callEndTimestamp = ""
    callUrl = ""

    callId = ""
    peerDisplay = ""
    closeReason = ""
    lastEventType = ""
    # What the endpoint announced itself as. Empty until baresip carries the
    # User-Agent header through to the event.
    peerUserAgent = ""
    # Which way each stream was agreed to run, from CALL_ESTABLISHED.
    mediaDir: Dict[str, str] = {}
    # What the gateway settled on: one audio line, one video line per stream.
    encoders: Dict[str, Any] = {}

    sourceUri = ""
    destinationUri = ""
    destinationDomain = ""
    destinationUriRaw = ""
    destinationRoomName = ""

    roomLineValue = ""
    browsingLineValue = ""
    sourceName = ""
    dtmfEvents: List[Dict[str, str]] = []
    media = MediaStats()
    mediaSamples: List[Dict[str, Any]] = []

    haveFinalCallClosed = False

    for historyLine in lines:
        historyLine = historyLine.strip()
        if not historyLine or ":" not in historyLine:
            continue

        recordType, recordPayload = historyLine.split(":", 1)
        recordType = recordType.strip()

        if recordType == "main_app":
            mainApp = (recordPayload or "").strip()
            continue

        try:
            recordData = json.loads(recordPayload)
        except Exception:
            continue

        if recordType == "call_start":
            callStartRaw = callStartRaw or (recordData.get("raw") or "")
            callStartTimestamp = callStartTimestamp or (recordData.get("timestamp") or "")
            if recordData.get("url"):
                callUrl = recordData.get("url") or ""
            if recordData.get("peerUserAgent"):
                peerUserAgent = recordData["peerUserAgent"]
            if recordData.get("mediaDir"):
                mediaDir = recordData["mediaDir"]

        elif recordType == "call_end":
            if recordData.get("raw"):
                callEndRaw = recordData.get("raw") or ""
            if recordData.get("timestamp"):
                callEndTimestamp = recordData.get("timestamp") or ""

        elif recordType == "encoder":
            # Not "media": that name holds the MediaStats object a few lines
            # above, and rebinding it here took the whole payload down with it.
            encoderMedia = (recordData.get("media") or "").strip()
            encoderValue = (recordData.get("value") or "").strip()
            if encoderMedia == "audio":
                encoders["audio"] = encoderValue
            elif encoderMedia == "video":
                encoders.setdefault("video", []).append(encoderValue)

        elif recordType == "room":
            roomLineValue = (recordData.get("value") or "").strip()
        elif recordType == "browsing":
            browsingLineValue = (recordData.get("value") or "").strip()

        elif recordType == "destination":
            if recordData.get("destinationURI"):
                destinationUri = (recordData.get("destinationURI") or "").strip()
            if recordData.get("destinationDomain"):
                destinationDomain = (recordData.get("destinationDomain") or "").strip()

        elif recordType == "call_closed":
            eventType = (recordData.get("lastEventType") or "").strip()
            isFinal = eventType == "CALL_CLOSED"

            if haveFinalCallClosed and not isFinal:
                continue
            if isFinal:
                haveFinalCallClosed = True

            callId = recordData.get("callId") or callId
            peerDisplay = (recordData.get("peerDisplayName") or peerDisplay).strip()
            closeReason = recordData.get("closeReason") or closeReason
            lastEventType = eventType or lastEventType

            if recordData.get("sourceURI"):
                sourceUri = normalizeSipUri(recordData["sourceURI"])
            if recordData.get("destinationURI"):
                destinationUriRaw = normalizeSipUri(recordData["destinationURI"])

        elif recordType == "dtmf":
            ts = recordData.get("timestamp") or ""
            inp = (recordData.get("input") or "").strip()
            if ts and inp:
                dtmfEvents.append({"timestamp": ts, "input": inp})

        elif recordType == "media_sample":
            mediaSamples.append({
                "seconds": recordData.get("seconds"),
                "video": recordData.get("video") or {},
            })

        elif recordType == "stats_value":
            mediaType = (recordData.get("media") or "").strip().lower()
            field = (recordData.get("field") or "").strip()
            tx = recordData.get("tx")
            rx = recordData.get("rx")
            if not mediaType or not field:
                continue

            if mediaType == "audio":
                if tx is not None:
                    media.audioTx[field] = tx
                if rx is not None:
                    media.audioRx[field] = rx

            elif mediaType == "video":
                streamIdxVal = recordData.get("streamIndex")
                try:
                    streamIdx = int(streamIdxVal) if streamIdxVal is not None else 0
                except Exception:
                    streamIdx = 0

                streamStats = media.videoStreams.setdefault(
                    streamIdx, {"streamIndex": streamIdx, "tx": {}, "rx": {}}
                )
                if tx is not None:
                    streamStats["tx"][field] = tx
                if rx is not None:
                    streamStats["rx"][field] = rx

    ### Get sourceName & destinationRoomName from URL ###
    urlDetails = parseCallUrlDetails(callUrl)
    if urlDetails.get("sourceName"):
        sourceName = urlDetails["sourceName"]
    if urlDetails.get("destinationRoomName"):
        destinationRoomName = urlDetails["destinationRoomName"]

    sourceUri = normalizeSipUri(sourceUri)

    ### Destination RAW data ###
    rawAor = stripSipPrefix(destinationUriRaw)
    rawDestAlias, rawDestAliasDomain = splitUri(destinationUriRaw)
    destinationDomainIp = rawDestAliasDomain or ""
    destinationGw = rawDestAlias or ""

    ### Remove sip: prefix ###
    destinationUri = stripSipPrefix(destinationUri)
    sourceNumber, sourceDomain = splitUri(sourceUri)

    ### Duration ###
    totalSeconds = 0
    totalMs = 0
    totalRaw = "00:00:00"

    startDate = parseIso(callStartTimestamp)
    endDate = parseIso(callEndTimestamp)
    if startDate and endDate and endDate >= startDate:
        dur = endDate - startDate
        sec = int(dur.total_seconds())
        totalSeconds = sec
        totalMs = sec * 1000
        totalRaw = f"{sec // 3600:02d}:{(sec % 3600) // 60:02d}:{sec % 60:02d}"

    mediaStats = {
        "audio": {"tx": media.audioTx, "rx": media.audioRx},
        "video": [media.videoStreams[i] for i in sorted(media.videoStreams)] if media.videoStreams else [],
        # The same figures over time, one reading every MEDIA_STATS_INTERVAL
        # seconds: totals say how the call went, these say when it went wrong.
        "samples": mediaSamples,
    }

    callObj = {
        "mainApp": mainApp,
        "callUrl": callUrl,
        "browsing": browsingLineValue,
        "room": roomLineValue,
        "roomType": roomType,
        "callSession": {
            "callStart": {"raw": callStartRaw, "timestamp": callStartTimestamp},
            "callEnd": {"raw": callEndRaw, "timestamp": callEndTimestamp},
            "totalTime": {"seconds": totalSeconds, "milliseconds": totalMs, "raw": totalRaw},
        },
        "details": {
            "callId": callId,
            "source": {
                "sourceURI": stripSipPrefix(sourceUri),
                "sourceName": sourceName,
                "sourceNumber": sourceNumber,
                "sourceDomain": sourceDomain,
            },
            "destination": {
                "destinationURI": destinationUri,
                "destinationRoomName": destinationRoomName,
                "destinationDomain": destinationDomain,

                "destinationDomainRaw": rawAor,
                "destinationGw": destinationGw,
                "destinationDomainIp": destinationDomainIp,
                "peerDisplayName": peerDisplay,
            },
            "closeReason": closeReason,
            "lastEventType": lastEventType,
            "peerUserAgent": peerUserAgent,
            "encoders": encoders,
            "mediaDir": mediaDir,
        },
        "dtmfEvents": dtmfEvents,
        "mediaStats": mediaStats,
        # What served the call, as opposed to what the call was.
        "gateway": gatewayVersions(),
    }

    jsonBody = {"call": callObj}
    return jsonBody


### Post ###
def pushHistory(historyPath: str) -> None:

    if not historyPath or not postUrl:
        return

    try:
        lines = readHistoryStable(historyPath, maxWaitS=5.0)
        if not lines:
            return

        payload = buildPayloadFromLines(lines, postUrl)
        headers = {"Accept": "text/plain"}
        if postToken:
            headers["Authorization"] = f"Bearer {postToken}"
        resp = requests.post(
            postUrl,
            json=payload,
            headers=headers,
            timeout=10,
        )

        if not (200 <= resp.status_code < 300):
            print(f"POST failed status={resp.status_code} body={resp.text!r}", file=sys.stderr, flush=True)
            return

        truncateHistory(historyPath)

    except Exception as exc:
        print("Failed to post call history:", exc, file=sys.stderr, flush=True)


### Main ###

def main() -> None:
    parser = argparse.ArgumentParser(description="Log parser")
    parser.add_argument("-p", "--pref", required=True, help="log prefix")
    parser.add_argument("-i", "--history", required=False, help="history file path")
    args = parser.parse_args()

    pref: str = args.pref
    historyFile: str = args.history or ""

    currentMedia: Optional[str] = None
    currentStream: Optional[int] = None
    videoAutoIndex = -1
    lastFinalCallId: Optional[str] = None

    gwStartLogged = False

    for raw in sys.stdin:
        cleaned = ansiEscapeRegex.sub("", raw)
        cleaned = cleaned.replace("\b", "").replace("\r", "\n")

        for line in cleaned.splitlines():
            line = line.strip()
            if not line:
                continue

            print(f"{pref}: {line}", flush=True)

            if not historyFile:
                continue

            try:
                ### Gateway start ###
                if (not gwStartLogged) and ("Web browsing URL:" in line):
                    dt = utcNow()
                    url = ""
                    if "URL:" in line:
                        url = line.split("URL:", 1)[1].strip()

                    appendHistory(
                        historyFile,
                        "gw_start",
                        {"raw": rawTimestamp(dt), "timestamp": isoZ(dt), "url": url},
                    )
                    gwStartLogged = True
                    continue

                ### Encoders ###
                # What the gateway settled on, printed once per stream as it
                # starts. The video line comes twice where a presentation
                # stream exists, the second being the slides.
                encMatch = encoderRegex.search(line.strip())
                if encMatch:
                    appendHistory(
                        historyFile,
                        "encoder",
                        {
                            "media": encMatch.group("media").lower(),
                            "value": encMatch.group("rest").strip(),
                        },
                    )
                    continue

                ### Room ###
                if "room:" in line:
                    appendHistory(historyFile, "room", {"value": line.split("room:", 1)[1].strip()})
                    continue

                ### Browsing ###
                if "browsing:" in line:
                    appendHistory(historyFile, "browsing", {"value": line.split("browsing:", 1)[1].strip()})
                    continue

                ### Event ###
                if pref == "Event":
                    dtmfMatch = dtmfRegex.match(line.strip())
                    if dtmfMatch:
                        dt = utcNow()
                        appendHistory(
                            historyFile,
                            "dtmf",
                            {"timestamp": isoZ(dt, ms=True), "input": dtmfMatch.group("input").strip()},
                        )
                        continue

                    eventDict = parseEventDict(line)

                    # The gateway's own reading of how the media is doing,
                    # printed every few seconds while the call is up. The
                    # call-end block says what the whole call averaged, which
                    # is what an incident does not look like: a stream that
                    # stops decoding halfway through leaves an impeccable
                    # average behind it.
                    if eventDict and eventDict.get("type") == "MEDIA_STATS":
                        appendHistory(historyFile, "media_sample", eventDict)
                        continue

                    if eventDict and eventDict.get("class") == "call":
                        lastType = str(eventDict.get("type") or "").strip()

                        ### Call established: trace the connected endpoint ###
                        if lastType == "CALL_ESTABLISHED":
                            appendHistory(
                                historyFile,
                                "call_start",
                                {
                                    "timestamp": isoZ(utcNow()),
                                    "callId": str(eventDict.get("id") or "").strip(),
                                    "sourceURI": normalizeSipUri(
                                        str(eventDict.get("peeruri") or "").strip()
                                    ),
                                    "peerDisplayName": str(
                                        eventDict.get("peerdisplayname") or ""
                                    ).strip(),
                                    # What the endpoint announced itself as.
                                    # Absent until the gateway's baresip
                                    # carries the header through.
                                    "peerUserAgent": str(
                                        eventDict.get("peeruseragent") or ""
                                    ).strip(),
                                    # Which way each stream was agreed to run.
                                    # A sendonly on one side is what an empty
                                    # picture looks like in the signalling.
                                    "mediaDir": {
                                        "audio": str(eventDict.get("audiodir") or "").strip(),
                                        "video": str(eventDict.get("videodir") or "").strip(),
                                        "remoteAudio": str(eventDict.get("remoteaudiodir") or "").strip(),
                                        "remoteVideo": str(eventDict.get("remotevideodir") or "").strip(),
                                        "localAudio": str(eventDict.get("localaudiodir") or "").strip(),
                                        "localVideo": str(eventDict.get("localvideodir") or "").strip(),
                                    },
                                },
                            )
                            continue

                        if lastType != "CALL_CLOSED":
                            continue

                        callId = str(eventDict.get("id") or "").strip()
                        if callId and callId == lastFinalCallId:
                            continue
                        if callId:
                            lastFinalCallId = callId

                        peeruri = str(eventDict.get("peeruri") or "").strip()
                        accountaor = str(eventDict.get("accountaor") or "").strip()
                        peerdisplay = str(eventDict.get("peerdisplayname") or "").strip()
                        closeReason = str(eventDict.get("param") or "").strip()

                        appendHistory(
                            historyFile,
                            "call_closed",
                            {
                                "callId": callId,
                                "peerDisplayName": peerdisplay,
                                "closeReason": closeReason,
                                "lastEventType": lastType,
                                "sourceURI": normalizeSipUri(peeruri),
                                "destinationURI": normalizeSipUri(accountaor),
                            },
                        )

                        dt = utcNow()
                        appendHistory(historyFile, "call_end", {"raw": rawTimestamp(dt), "timestamp": isoZ(dt)})

                        pushHistory(historyFile)
                        continue

                ### Baresip ###
                if pref == "Baresip":
                    callLineMatch = baresipRegex.match(line.strip())
                    if callLineMatch:
                        destUser = callLineMatch.group("dest_user")
                        destDom = callLineMatch.group("dest_dom")
                        appendHistory(
                            historyFile,
                            "destination",
                            {
                                "destinationURI": f"{destUser}@{destDom}",
                                "destinationRoomName": destUser,
                                "destinationDomain": destDom,
                            },
                        )
                        continue

                    ### QOS ###
                    statsHeaderMatch = statHeaderRegex.match(line.strip())
                    if statsHeaderMatch:
                        currentMedia = statsHeaderMatch.group("media").strip().lower()
                        if currentMedia == "video":
                            streamS = statsHeaderMatch.group("stream")
                            if streamS is not None:
                                currentStream = int(streamS)
                                videoAutoIndex = max(videoAutoIndex, currentStream)
                            else:
                                videoAutoIndex += 1
                                currentStream = videoAutoIndex
                        else:
                            currentStream = None
                        continue

                    ### QOS values ###
                    statsValueMatch = statValueRegex.match(line.strip())
                    if statsValueMatch and currentMedia in ("audio", "video"):
                        label = statsValueMatch.group("label").strip()
                        if label in fieldMap:
                            nums = numRegex.findall(statsValueMatch.group("rest"))
                            tx = toNumber(nums[0]) if len(nums) >= 1 else None
                            rx = toNumber(nums[1]) if len(nums) >= 2 else None
                            appendHistory(
                                historyFile,
                                "stats_value",
                                {
                                    "media": currentMedia,
                                    "streamIndex": currentStream,
                                    "field": fieldMap[label],
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
                        dt = utcNow()
                        appendHistory(historyFile, "call_end", {"raw": rawTimestamp(dt), "timestamp": isoZ(dt)})
                        pushHistory(historyFile)
                        continue

            except Exception as exc:
                print("Failed to parse log line:", exc, file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
