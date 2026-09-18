#!/usr/bin/env python
"""
baresip's control port, and what it prints back.

Commands are sent as a line on a local socket; some return nothing worth
reading, some return a block of text to be picked apart. Both live here rather
than in event_handler, which has the gateway's own logic to hold, and rather
than in logParse, which digests a stream of log lines at the far end of the
chain and does not run commands.
"""
import re
import subprocess


class BaresipCmd:
    """One gateway's control port."""

    def __init__(self, host="127.0.0.1", port=5555, timeout=5):
        self.host = host
        self.port = port
        self.timeout = timeout

    def send(self, command):
        """Send a command and hand back what it printed, or '' on failure.

        A command the port cannot answer is not an error here: the call may
        have ended, or baresip may be on its way out.
        """
        try:
            out = subprocess.run(
                ['echo "%s" | netcat -q 1 %s %d' % (command, self.host, self.port)],
                shell=True, capture_output=True, text=True, timeout=self.timeout,
            )
            return out.stdout or ""
        except Exception as exc:
            print("BaresipCmd: %s did not answer: %s" % (command, exc), flush=True)
            return ""

    def videoStats(self, callSeconds=None):
        """What /video_debug says, per stream, by the name its header carries.

        One block on a plain call, two once a presentation is in play — a
        stream that does not exist prints nothing at all, so the blocks are
        read by their header rather than counted.
        """
        text = self.send("/video_debug")
        if not text:
            return {}

        stats = {}
        for name, lines in self._streams(text).items():
            stream = self._readStream(lines, callSeconds)
            buffer = self._readJitterBuffer("\n".join(lines))
            if buffer:
                stream["jitterBuffer"] = buffer
            stats[name] = stream
        return stats

    @staticmethod
    def _streams(text):
        """Split the output into one list of lines per video stream.

        Everything up to the next stream header belongs to the current one,
        the Stream debug and jitter buffer blocks included: each stream has
        its own.
        """
        streams = {}
        name = None
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("---") and stripped.endswith("video stream ---"):
                name = stripped.strip("- ").replace(" video stream", "").strip()
                streams[name] = []
            elif name is not None:
                streams[name].append(line)
        return streams

    @staticmethod
    def _readStream(lines, callSeconds):
        """What one video block says, as far as it can be trusted.

        Values are matched by name rather than counted: the source is called
        x11grab and the display x11, and a reader that takes the numbers in
        order ends up with 11 for a width.

        The transmit clock of an avformat source starts from an absolute
        instant rather than from zero, which puts it some six million years
        ahead. Any duration longer than the call is dropped rather than
        carried into a rate nobody could read.
        """
        stats = {}
        section = None
        for line in lines:
            stripped = line.strip()
            if stripped.startswith("tx:"):
                section = "tx"
                continue
            if stripped.startswith("rx:"):
                section = "rx"
                continue
            if section is None:
                continue

            if stripped.startswith("source:") and section == "tx":
                # One tx can list several sources while a switch is in
                # progress; the first is the one in use.
                if "source" in stats:
                    continue
                got = re.match(r"source:\s*(\S+)\s+(\d+)\s*x\s*(\d+),"
                               r"\s*fps=([\d.]+)\s+frames=(\d+)", stripped)
                if got:
                    stats["source"] = got.group(1)
                    stats["txWidth"] = int(got.group(2))
                    stats["txHeight"] = int(got.group(3))
                    stats["txFps"] = float(got.group(4))
                    stats["txFrames"] = int(got.group(5))
            elif stripped.startswith("skipc=") and section == "tx":
                got = re.match(r"skipc=(\d+)\s+sendq=(\d+)", stripped)
                if got:
                    stats["txSkipped"] = int(got.group(1))
                    stats["txQueued"] = int(got.group(2))
            elif stripped.startswith("vidisp:") and section == "rx":
                got = re.match(r"vidisp:\s*\S+\s+(\d+)\s*x\s*(\d+)\s+frames=(\d+)",
                               stripped)
                if got:
                    stats["rxWidth"] = int(got.group(1))
                    stats["rxHeight"] = int(got.group(2))
                    stats["rxFrames"] = int(got.group(3))
            elif stripped.startswith("n_keyframes") and section == "rx":
                got = re.match(r"n_keyframes=(\d+),\s*n_picup=(\d+)", stripped)
                if got:
                    stats["rxKeyframes"] = int(got.group(1))
                    stats["rxPicup"] = int(got.group(2))
            elif stripped.startswith("time ="):
                if "not started" in stripped:
                    stats[section + "Seconds"] = 0
                    continue
                got = re.match(r"time\s*=\s*([\d.]+)", stripped)
                if got:
                    seconds = float(got.group(1))
                    if not callSeconds or seconds <= callSeconds + 60:
                        stats[section + "Seconds"] = seconds
        return stats

    @staticmethod
    def _readJitterBuffer(text):
        """Frames waiting in the jitter buffer, and the ceiling they may reach.

        The line reads "running=1 min=1 cur=3/5 max=100": cur carries both
        frames and packets, so the fields are named rather than counted.
        """
        for line in text.splitlines():
            got = re.match(r"running=(\d+)\s+min=(\d+)\s+cur=(\d+)/(\d+)\s+max=(\d+)",
                           line.strip())
            if got:
                return {"running": int(got.group(1)), "min": int(got.group(2)),
                        "currentFrames": int(got.group(3)),
                        "currentPackets": int(got.group(4)),
                        "max": int(got.group(5))}
        return {}
