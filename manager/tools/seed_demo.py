#!/usr/bin/env python3
"""
Fill a month with plausible traffic, so the front can be looked at before
production data exists.

Every call it writes carries the marker below, in call_id and in gw_alias:
seeded calls are told apart from real ones by something visible in the data,
not by a date range someone has to remember. Pool samples carry no marker:
they are replaced for the whole month, so a month that already holds samples
(real readings, on a live database) is refused unless --replace-samples says
so.

    python3 tools/seed_demo.py --month 2026-08            # write
    python3 tools/seed_demo.py --month 2026-08 --clear    # remove, then write
    python3 tools/seed_demo.py --clear-only               # remove everything seeded
    ... --replace-samples                                  # also overwrite / remove that month's samples

The generated shape is deliberately ordinary: a morning peak, a lunch dip, a
second afternoon peak, nothing on weekends beyond a trickle. Enough for the
charts to have a shape worth reading, not enough to be mistaken for a
measurement.
"""

import argparse
import json
import os
import random
import sys
from datetime import datetime, timedelta, timezone

MARKER = "demo-seed"

# Connector mix, roughly what a ministry pool shows: one dominant platform, a
# long tail. Weights are relative, not percentages.
PLATFORMS = [("visio", 62), ("jitsi", 14), ("webinaire", 9),
             ("teams", 7), ("bigbluebutton", 5), ("googlemeet", 3)]

ORG_UNITS = [("SALES", 46), ("SUPPORT", 22), ("FINANCE", 18), ("HR", 14)]

# How a call ends. `room` is what decides the outcome: the trigger reads it, so
# a seeded row is classified by the same rule as a real one rather than having
# its outcome written in.
ENDINGS = [
    ("Connection reset by peer [104]", True, 58),
    ("Connection reset by user", True, 27),
    ("Connection reset by user", False, 7),     # hung up on the voice menu
    ("Connection reset by peer [104]", False, 5),
    ("rtp stream error", True, 2),              # counted as a technical failure
    ("Connection timed out", False, 1),
]

# Concurrent calls by hour on a working day, before the day-to-day noise. The
# floor above it is what the pool has to carry.
# Calls started per hour on a working day, scaled so the month lands near the
# real figures the platform reports: about 2 600 calls, 3 200 hours of
# conference, a peak in the low forties.
HOURLY_SHAPE = [0, 0, 0, 0, 0, 0, 1, 2, 5, 15, 21, 13,
                4, 8, 17, 22, 11, 5, 2, 1, 1, 0, 0, 0]


def weighted(pairs, rng):
    total = sum(w for _, w in pairs)
    mark = rng.uniform(0, total)
    for value, weight in pairs:
        mark -= weight
        if mark <= 0:
            return value
    return pairs[-1][0]


def monthRange(month):
    start = datetime.strptime(month, "%Y-%m").replace(tzinfo=timezone.utc)
    end = (start.replace(day=28) + timedelta(days=8)).replace(day=1)
    return start, end


def buildCalls(start, end, rng):
    """One row per call, with the columns logParse would have pushed."""
    rows = []
    day = start
    while day < end:
        weekend = day.weekday() >= 5
        # The load varies by the day, not by the hour: drawn per hour it would
        # average out, and the month would have no busy days at all — which is
        # precisely what the peak figures are about. Roughly one day in twelve
        # carries something large, a plenary or a webinar.
        dayFactor = rng.uniform(0.55, 1.5)
        if rng.random() < 0.08:
            dayFactor *= rng.uniform(1.8, 2.4)
        for hour in range(24):
            expected = HOURLY_SHAPE[hour] * (0.06 if weekend else 1.0) * dayFactor
            for _ in range(int(round(expected))):
                # Meetings start on the hour and on the half hour, and that
                # clustering is what produces the peaks: spread evenly across
                # the hour, the same volume would never show one.
                minute = rng.choices(
                    [rng.randint(0, 3), rng.randint(28, 33), rng.randint(0, 59),
                     rng.randint(14, 17), rng.randint(43, 47)],
                    weights=[42, 24, 14, 12, 8])[0]
                startedAt = day + timedelta(hours=hour, minutes=min(59, minute),
                                            seconds=rng.randint(0, 59))
                # Durations: mostly half-hour and hour meetings, a tail of long
                # ones, and the short sessions that never joined.
                reason, joined, _ = rng.choices(ENDINGS, weights=[e[2] for e in ENDINGS])[0]
                if joined:
                    # Real traffic averages a little over an hour: half-hour
                    # stand-ups exist but the bulk are hour-long meetings, with a
                    # tail of half-days that pulls the mean well above the median.
                    duration = int(rng.choices(
                        [rng.gauss(1750, 400), rng.gauss(3500, 700),
                         rng.gauss(5400, 1100), rng.gauss(12000, 2600)],
                        weights=[26, 44, 22, 8])[0])
                    duration = max(60, duration)
                else:
                    duration = rng.randint(8, 95)
                platform = weighted(PLATFORMS, rng)
                unit = weighted(ORG_UNITS, rng)
                roomId = f"{rng.randint(100000000, 999999999)}" if joined else None
                # Occupancy exceeds duration: the container is up before the call
                # is answered and released after it ends.
                occupancy = duration + rng.randint(12, 40)
                number = f"{rng.randint(10, 89)}{rng.randint(100, 999)}"
                rows.append({
                    "call_id": f"{MARKER}-{len(rows):06d}",
                    "gw_alias": f"{MARKER}-gw{rng.randint(0, 7)}",
                    "main_app": "baresip",
                    "platform": platform,
                    "room": roomId,
                    "source_uri": f"sip:{number}@rooms.{unit.lower()}.example.org",
                    "source_name": f"Room {rng.choice(['Jupiter', 'Saturn', 'Vega', 'Altair', 'Rigel', 'Mizar'])}",
                    "source_number": number,
                    "source_domain": f"rooms.{unit.lower()}.example.org",
                    "destination_uri": f"sip:{roomId or 'ivr'}@visio.example.org",
                    "peer_display_name": f"Room {number}",
                    "call_start": startedAt,
                    "call_end": startedAt + timedelta(seconds=occupancy),
                    "duration_s": duration,
                    "occupancy_s": occupancy,
                    "close_reason": reason,
                    "org_unit": unit,
                })
        day += timedelta(days=1)
    return rows


def buildSamples(start, end, calls, rng):
    """
    Pool readings every minute, derived from the calls themselves.

    Counting the calls in flight at each minute keeps the two sources telling the
    same story: a peak in the call log has to be visible in the pool, or the
    sizing table and the usage tiles would contradict each other.
    """
    busyAt = {}
    for call in calls:
        minute = call["call_start"].replace(second=0, microsecond=0)
        last = call["call_end"].replace(second=0, microsecond=0)
        while minute <= last:
            busyAt[minute] = busyAt.get(minute, 0) + 1
            minute += timedelta(minutes=1)

    samples, moment = [], start
    while moment < end:
        busy = busyAt.get(moment, 0)
        # The floor the scaler holds: generous during office hours, minimal at
        # night. Warm containers sit above the busy count, and a few VMs stay
        # provisioned with nothing running on them.
        hour, weekend = moment.hour, moment.weekday() >= 5
        floor = 5 if weekend else (40 if 8 <= hour < 18 else 5)
        running = max(busy, min(floor, busy + rng.randint(2, 6)))
        ivr = min(busy, rng.randint(0, 2)) if busy else 0
        samples.append({
            "ts": moment,
            "interval_s": 60,
            "free": max(0, floor - running) + rng.randint(0, 2),
            "idle": max(0, running - busy),
            "ivr": ivr,
            "in_call": max(0, busy - ivr),
        })
        moment += timedelta(minutes=1)
    return samples


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--month", help="month to fill, as YYYY-MM")
    parser.add_argument("--clear", action="store_true", help="remove seeded rows first")
    parser.add_argument("--clear-only", action="store_true", help="remove seeded rows and stop")
    parser.add_argument("--replace-samples", action="store_true",
                        help="overwrite the month's pool samples (and remove them on --clear); "
                             "they may be real readings")
    parser.add_argument("--dsn", default=os.getenv("DATABASE_URL"))
    parser.add_argument("--seed", type=int, default=20260801,
                        help="fixed by default, so two runs give the same month")
    args = parser.parse_args()

    if not args.dsn:
        sys.exit("DATABASE_URL is not set and --dsn was not given")
    if not args.month and not args.clear_only:
        sys.exit("--month is required unless --clear-only")

    import psycopg

    with psycopg.connect(args.dsn) as connection:
        with connection.cursor() as cursor:
            if args.clear or args.clear_only:
                # The months are read before the calls go: read after, the
                # seeded calls are gone and no month is found.
                cursor.execute("""
                    SELECT DISTINCT date_trunc('month', call_start)
                      FROM calls WHERE call_id LIKE %s AND call_start IS NOT NULL
                """, (f"{MARKER}-%",))
                months = [row[0] for row in cursor.fetchall()]
                cursor.execute("DELETE FROM calls WHERE call_id LIKE %s", (f"{MARKER}-%",))
                print(f"removed {cursor.rowcount} seeded calls")
                if months and args.replace_samples:
                    cursor.execute("DELETE FROM pool_samples WHERE date_trunc('month', ts) = ANY(%s)",
                                   (months,))
                    print(f"removed {cursor.rowcount} pool samples of the seeded months")
                elif months:
                    print("pool samples of the seeded months kept (they may be real): "
                          "--replace-samples removes them")
                if args.clear_only:
                    connection.commit()
                    return

            rng = random.Random(args.seed)  # nosec B311 - reproducible demo data, not a secret
            start, end = monthRange(args.month)
            cursor.execute("SELECT count(*) FROM pool_samples WHERE ts >= %s AND ts < %s", (start, end))
            existing = cursor.fetchone()[0]
            if existing and not args.replace_samples:
                sys.exit(f"{existing} pool samples already in {args.month}, perhaps real readings: "
                         "nothing written. --replace-samples overwrites them.")
            calls = buildCalls(start, end, rng)
            samples = buildSamples(start, end, calls, rng)

            # Samples for the month are replaced wholesale: leaving real readings
            # underneath would mix measured and invented figures in one chart.
            cursor.execute("DELETE FROM pool_samples WHERE ts >= %s AND ts < %s", (start, end))

            for call in calls:
                columns = list(call) + ["raw"]
                values = [call[c] for c in call] + [json.dumps({"seeded": True})]
                # nosemgrep: mgr-sql-built-by-hand
                cursor.execute(
                    f"INSERT INTO calls ({', '.join(columns)}) "  # nosec B608  # names from buildCalls()
                    f"VALUES ({', '.join(['%s'] * len(columns))})", values)

            cursor.executemany(
                "INSERT INTO pool_samples (ts, interval_s, free, idle, ivr, in_call) "
                "VALUES (%(ts)s, %(interval_s)s, %(free)s, %(idle)s, %(ivr)s, %(in_call)s) "
                "ON CONFLICT (ts) DO UPDATE SET free = EXCLUDED.free, idle = EXCLUDED.idle, "
                "ivr = EXCLUDED.ivr, in_call = EXCLUDED.in_call", samples)

        connection.commit()

    joined = sum(1 for c in calls if c["room"])
    hours = sum(c["duration_s"] for c in calls if c["room"]) / 3600
    print(f"{args.month}: {len(calls)} calls, {joined} joined, {hours:.0f} h of conference, "
          f"{len(samples)} pool samples")
    print(f"peak concurrent: {max(s['ivr'] + s['in_call'] for s in samples)}")
    print(f"\nremove with: python3 {sys.argv[0]} --clear-only")


if __name__ == "__main__":
    main()
