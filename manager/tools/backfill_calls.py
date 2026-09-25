#!/usr/bin/env python3
"""
Brings the calls already stored in line with the ingestion (P15, P16), from
their raw payload.

    docker compose exec manager python tools/backfill_calls.py           # dry run
    docker compose exec manager python tools/backfill_calls.py --apply

Four steps, in one transaction. The dry run performs them all and rolls back,
so the counts it prints are the ones --apply will produce, not an estimate.

  1. Empty pushes (no Call-ID and no start): deleted. A gateway container
     stopping without having carried a call; the ingestion now refuses them.
  2. Calls with a Call-ID and no start: marked not established, dated by
     their reception, then recompute_outcomes() classifies them. A replayed
     push of the same Call-ID is deleted, the first one kept.
  3. The fields pushed since SIPMediaGW #101, #102 and #105 (peer, codecs,
     media direction, versions, sample summary) copied into their columns.
  4. Video statistics duplicated by #101 (one pair per sample, all cumulative)
     reduced to the last pair, the one written at hang-up. Calls from 15/09
     pushed before samples were in the payload are recognised by their
     counters, which never decrease from one pair to the next; the same
     shape before 15/09 is only reported, never changed.

Replayable: a second run finds nothing left to do. Reads DATABASE_URL inside
the container, like the application.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg                                   # noqa: E402
from psycopg.types.json import Jsonb             # noqa: E402

from ingest.mapping import (                     # noqa: E402
    isRepeated, looksCumulative, mediaDetails, mediaRows,
)

# The first gateway image of the #101 branch ran on the lab from this date.
ARTIFACT_SINCE = "2026-09-15"

DETAIL_COLUMNS = (
    "peer_user_agent", "audio_codec", "video_codec", "video_encoder",
    "gw_version", "baresip_version", "baresip_patch", "chromium_version",
    "video_state", "video_min_rx_fps", "video_low_intervals",
    "video_keyframe_requests", "presentation_s",
)

DETAIL_TYPES = {
    "video_min_rx_fps": "numeric", "video_low_intervals": "integer",
    "video_keyframe_requests": "integer", "presentation_s": "integer",
    "media_direction": "jsonb",
}

INSERT_MEDIA = """
    INSERT INTO call_media_stats
        (call_pk, media, stream_index, direction, packets, errors,
         packet_reports, avg_bitrate_kbps, lost_packets, jitter_ms)
    VALUES (%(call_pk)s, %(media)s, %(stream_index)s, %(direction)s, %(packets)s,
            %(errors)s, %(packet_reports)s, %(avg_bitrate_kbps)s,
            %(lost_packets)s, %(jitter_ms)s)
"""


def emptyPushes(cur):
    cur.execute("DELETE FROM calls WHERE call_id IS NULL AND call_start IS NULL RETURNING id")
    return [row[0] for row in cur.fetchall()]


def notEstablished(cur):
    # Replays first: the unique index on Call-ID for calls not established
    # would refuse the second row of a pair.
    cur.execute("""
        DELETE FROM calls c
         WHERE c.call_id IS NOT NULL AND c.call_start IS NULL
           AND EXISTS (SELECT 1 FROM calls o
                        WHERE o.call_id = c.call_id AND o.call_start IS NULL AND o.id < c.id)
        RETURNING id""")
    replays = [row[0] for row in cur.fetchall()]
    cur.execute("""
        UPDATE calls SET established = false, call_start = received_at
         WHERE call_id IS NOT NULL AND call_start IS NULL
        RETURNING id""")
    marked = [row[0] for row in cur.fetchall()]
    cur.execute("SELECT rows_moved FROM recompute_outcomes('P15: calls not established')")
    moved = cur.fetchone()[0]
    return marked, replays, moved


def details(cur):
    """Only the calls whose payload carries at least one of the new fields."""
    cur.execute("""
        SELECT id, raw FROM calls
         WHERE raw->'call'->'details' ? 'peerUserAgent'
            OR raw->'call'->'details' ? 'encoders'
            OR raw->'call'->'details' ? 'mediaDir'
            OR raw->'call' ? 'gateway'
            OR raw->'call'->'mediaStats' ? 'samples'
         ORDER BY id""")
    rows = cur.fetchall()
    # Typed placeholders: the comparison below needs a type for a NULL.
    columns = DETAIL_COLUMNS + ("media_direction",)
    placeholders = [f"%s::{DETAIL_TYPES.get(name, 'text')}" for name in columns]
    assignments = ", ".join(f"{name} = {ph}" for name, ph in zip(columns, placeholders))
    changed = 0
    for callPk, raw in rows:
        row = mediaDetails(raw)
        direction = row["media_direction"]
        values = [row[name] for name in DETAIL_COLUMNS] + [Jsonb(direction) if direction is not None else None]
        # Only a row whose values differ is written, so a second run says 0.
        # The names and casts come from DETAIL_COLUMNS / DETAIL_TYPES, constants
        # of this file; the values travel as parameters.
        # nosemgrep: mgr-sql-built-by-hand
        cur.execute(f"""
            UPDATE calls SET {assignments}
             WHERE id = %s AND ({', '.join(columns)}) IS DISTINCT FROM ({', '.join(placeholders)})
            RETURNING id""", values + [callPk] + values)  # nosec B608  # constant names
        changed += len(cur.fetchall())
    return len(rows), changed


def videoArtifacts(cur):
    cur.execute("""
        SELECT c.id, c.received_at, c.raw->'call'->'mediaStats',
               (SELECT count(*) FROM call_media_stats m
                 WHERE m.call_pk = c.id AND m.media = 'video')
          FROM calls c
         WHERE jsonb_typeof(c.raw->'call'->'mediaStats'->'video') = 'array'
           AND jsonb_array_length(c.raw->'call'->'mediaStats'->'video') >= 4
         ORDER BY c.id""")
    rewritten, reportedOnly = [], []
    for callPk, receivedAt, mediaStats, storedRows in cur.fetchall():
        video = mediaStats.get("video") or []
        samples = mediaStats.get("samples")
        bySamples = isRepeated(mediaStats)          # the ingestion's own rule
        byCounters = not isinstance(samples, list) and looksCumulative(video)
        if not (bySamples or byCounters):
            continue
        if byCounters and receivedAt.date().isoformat() < ARTIFACT_SINCE:
            reportedOnly.append(callPk)
            continue
        if byCounters:
            # Present the entries as the ingestion rule expects them: it then
            # keeps the last pair, exactly as it does for a live push.
            mediaStats = dict(mediaStats, samples=[{}] * (len(video) // 2 - 1))
        rows = [row for row in mediaRows(mediaStats) if row["media"] == "video"]
        if storedRows == len(rows):
            continue                                # already reduced: replayed run
        cur.execute("DELETE FROM call_media_stats WHERE call_pk = %s AND media = 'video'", (callPk,))
        for row in rows:
            cur.execute(INSERT_MEDIA, {"call_pk": callPk, **row})
        rewritten.append((callPk, len(video), len(rows)))
    return rewritten, reportedOnly


def sample(ids, limit=10):
    shown = ", ".join(str(i) for i in ids[:limit])
    return shown + (" …" if len(ids) > limit else "")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="commit (without it: dry run, rolled back)")
    args = parser.parse_args()

    url = os.getenv("DATABASE_URL", "")
    if not url:
        sys.exit("DATABASE_URL is not set")
    with psycopg.connect(url, options="-c statement_timeout=0") as conn:
        with conn.cursor() as cur:
            deleted = emptyPushes(cur)
            print(f"1. empty pushes deleted               : {len(deleted)}  [{sample(deleted)}]")
            marked, replays, moved = notEstablished(cur)
            print(f"2. marked not established             : {len(marked)}  [{sample(marked)}]")
            print(f"   replayed pushes deleted            : {len(replays)}  [{sample(replays)}]")
            print(f"   outcomes moved by recompute        : {moved}")
            carrying, filled = details(cur)
            print(f"3. calls carrying the new fields      : {carrying}, columns filled: {filled}")
            rewritten, reportedOnly = videoArtifacts(cur)
            print(f"4. video statistics reduced           : {len(rewritten)} calls")
            for callPk, before, after in rewritten[:10]:
                print(f"     call {callPk}: {before} entries -> {after} rows")
            if len(rewritten) > 10:
                print(f"     … and {len(rewritten) - 10} more")
            print(f"   same shape before {ARTIFACT_SINCE}, left alone: {len(reportedOnly)}  [{sample(reportedOnly)}]")
        if args.apply:
            conn.commit()
            print("applied")
        else:
            conn.rollback()
            print("dry run: nothing written (rerun with --apply)")


if __name__ == "__main__":
    main()
