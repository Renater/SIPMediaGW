"""
Pool sampler: records how many gateways are running, and in which state,
at a fixed interval.

Call logs cannot cost the pool — a pre-provisioned gateway that waits for hours
without a call pushes nothing. The proxyAPI sees every gateway from /register
to its disappearance, so sampling its view integrates the real occupancy.
Gateway-hours = sum(count x interval); a gap (Manager down) counts for nothing,
which under-estimates rather than invents.
"""

import asyncio
import datetime as dt
import logging
import os

from api.park import fetchStatuses
from db import DatabaseUnavailable, connection

log = logging.getLogger("manager.sampler")

intervalSeconds = int(os.getenv("POOL_SAMPLE_INTERVAL", "60"))

INSERT_SAMPLE = """
    INSERT INTO pool_samples (ts, interval_s, free, idle, ivr, in_call)
    VALUES (%s, %s, %s, %s, %s, %s)
    ON CONFLICT (ts) DO NOTHING
"""


def _store(sample):
    with connection() as conn:
        conn.execute(INSERT_SAMPLE, (
            sample["ts"], intervalSeconds,
            sample["free"], sample["idle"], sample["ivr"], sample["in_call"],
        ))


async def sampleOnce():
    """One reading of the pool, stored with the interval it stands for."""
    statuses = await fetchStatuses()
    counts = {"free": 0, "idle": 0, "ivr": 0, "in_call": 0}
    for gateway in statuses["gateways"]:
        key = "in_call" if gateway["state"] == "call" else gateway["state"]
        if key in counts:
            counts[key] += 1
    sample = {"ts": dt.datetime.now(dt.timezone.utc).replace(microsecond=0), **counts}
    await asyncio.to_thread(_store, sample)
    return sample


async def run():
    """Background loop; one failure never stops the next reading."""
    if intervalSeconds <= 0:
        log.info("pool sampler disabled (POOL_SAMPLE_INTERVAL=%s)", intervalSeconds)
        return
    log.info("pool sampler started, every %ss", intervalSeconds)
    skipped = 0
    while True:
        try:
            sample = await sampleOnce()
            log.debug("pool sample %s", sample)
            if skipped:
                log.info("pool sampling resumed after %d skipped", skipped)
            skipped = 0
        except DatabaseUnavailable:
            skipped += 1
            _skipped(skipped, "database unavailable")
        except Exception as exc:                        # proxy down, timeout…
            skipped += 1
            _skipped(skipped, f"{exc} ({exc.__cause__})" if exc.__cause__ else exc)
        await asyncio.sleep(intervalSeconds)


def _skipped(count, reason):
    """
    The first miss is worth a warning; the sixtieth of the same hour is not.
    An outage reads as one WARNING, DEBUG lines under it, one INFO at the end.
    """
    level = logging.WARNING if count == 1 else logging.DEBUG
    log.log(level, "pool sample skipped (%d in a row): %s", count, reason)
