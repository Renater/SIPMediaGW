#!/usr/bin/env python
"""Cinder volume handling for the OpenStack provider."""

import logging
import time

from .errors import isNotFoundError

logger = logging.getLogger(__name__)

# A volume stays "in-use" for a while after its server is deleted, so deletion
# is retried rather than attempted once.
_MAX_DELETE_ATTEMPTS = 6
_DELETE_RETRY_DELAY = 10


def getServerVolumeIds(conn, server):
    """Return the ids of the volumes attached to `server`."""
    serverId = getattr(server, "id", "?")
    volumeIds = []

    try:
        for vol in getattr(server, "attached_volumes", None) or []:
            volId = vol.get("id") if isinstance(vol, dict) else getattr(vol, "id", None)
            if volId:
                volumeIds.append(volId)
    except Exception as exc:
        logger.warning("Cannot list attached volumes for server %s: %s", serverId, exc)

    # The server detail response does not always carry the attachments, so fall
    # back to the dedicated Nova call.
    if not volumeIds:
        try:
            for attachment in conn.compute.volume_attachments(server):
                volId = getattr(attachment, "volume_id", None)
                if volId:
                    volumeIds.append(volId)
        except Exception as exc:
            logger.warning("Cannot list volume attachments for server %s: %s", serverId, exc)

    logger.debug("Server %s has volumes: %s", serverId, volumeIds)
    return volumeIds


def _tryDeleteVolume(conn, volId, attempt):
    """
    Attempt one deletion of `volId`.
    Returns "deleted", "absent", "pending" or "failed".
    """
    try:
        vol = conn.block_storage.find_volume(volId, ignore_missing=True)
        if not vol:
            return "absent"

        status = (getattr(vol, "status", "") or "").lower()
        if status == "in-use":
            logger.info(
                "Volume %s still in-use on attempt %s/%s, will retry",
                volId, attempt + 1, _MAX_DELETE_ATTEMPTS,
            )
            return "pending"

        conn.block_storage.delete_volume(volId, ignore_missing=True)
        logger.info("Delete request sent for volume %s (status=%s)", volId, status or "unknown")
        return "deleted"

    except Exception as exc:
        if isNotFoundError(exc):
            return "absent"
        if attempt < (_MAX_DELETE_ATTEMPTS - 1):
            logger.warning(
                "Volume %s delete failed on attempt %s/%s, retrying: %s",
                volId, attempt + 1, _MAX_DELETE_ATTEMPTS, exc,
            )
            return "pending"
        logger.error(
            "Volume %s delete failed after %s attempts: %s",
            volId, _MAX_DELETE_ATTEMPTS, exc,
        )
        return "failed"


def deleteVolumes(conn, volumeIds):
    """Delete every volume in `volumeIds`, retrying while they remain in-use."""
    remaining = list(dict.fromkeys(volumeIds))
    if not remaining:
        logger.info("No attached volumes queued for deletion")
        return

    requested = len(remaining)
    logger.info("Starting volume deletion for %s volume(s): %s", requested, remaining)
    deleted = []
    alreadyGone = []
    failed = []

    for attempt in range(_MAX_DELETE_ATTEMPTS):
        if not remaining:
            break
        if attempt > 0:
            time.sleep(_DELETE_RETRY_DELAY)
        logger.info(
            "Volume deletion attempt %s/%s for %s pending volume(s)",
            attempt + 1, _MAX_DELETE_ATTEMPTS, len(remaining),
        )

        stillPending = []
        for volId in remaining:
            outcome = _tryDeleteVolume(conn, volId, attempt)
            if outcome == "deleted":
                deleted.append(volId)
            elif outcome == "absent":
                logger.info("Volume %s already absent (treated as deleted)", volId)
                alreadyGone.append(volId)
            elif outcome == "pending":
                stillPending.append(volId)
            else:
                failed.append(volId)
        remaining = stillPending

    failed.extend(volId for volId in remaining if volId not in failed)

    logger.info(
        "Volume deletion summary: requested=%s, deleted=%s, already_deleted=%s, failed=%s",
        requested, len(deleted), len(alreadyGone), len(failed),
    )
    if failed:
        logger.warning("Volume deletion failed for IDs: %s", failed)
