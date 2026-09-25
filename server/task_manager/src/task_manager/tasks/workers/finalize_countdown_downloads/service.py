from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Episode
from backend.db.models.media_download import EpisodeMediaDownload
from backend.types.episode_types import EpisodePublishStatus
from task_manager.scheduler.operation_control import cancel_operation
from task_manager.scheduler.results import TaskResult
from task_manager.tasks.media_download_operations import (
    dispatch_queued_media_download_operations,
    get_active_media_download_operation,
    queue_final_episode_redownload_if_ready,
)


_CANCEL_REASON = "Final episode media became available"


def _candidate_download_ids(s: Session, *, episode_id: int | None) -> list[int]:
    stmt = (
        select(EpisodeMediaDownload.id)
        .join(Episode, Episode.id == EpisodeMediaDownload.media_item_id)
        .where(
            EpisodeMediaDownload.redownload_when_final.is_(True),
            Episode.publish_status == EpisodePublishStatus.PUBLISHED_FINAL.value,
        )
    )
    if episode_id is not None:
        stmt = stmt.where(Episode.id == episode_id)
    return list(s.scalars(stmt))


async def run_finalize_countdown_downloads(
    s: Session,
    *,
    episode_id: int | None = None,
) -> TaskResult:
    """Consume durable countdown-replacement intent after final media is published.

    The episode publication event is the normal trigger. App startup performs
    the same query globally so a restart between persistence of the intent and
    event handling cannot strand a countdown artifact indefinitely.
    """
    candidate_ids = _candidate_download_ids(s, episode_id=episode_id)
    s.rollback()

    queued = 0
    canceled = 0

    for download_id in candidate_ids:
        download = s.get(EpisodeMediaDownload, download_id)
        if download is None or not download.redownload_when_final:
            s.rollback()
            continue

        episode = s.get(Episode, download.media_item_id)
        if episode is None or episode.publish_status != EpisodePublishStatus.PUBLISHED_FINAL.value:
            s.rollback()
            continue

        active = get_active_media_download_operation(s, download.id)
        if (
            active is not None
            and isinstance(active.context, dict)
            and active.context.get("episode_publish_status")
            == EpisodePublishStatus.PUBLISHED_FINAL.value
        ):
            queue_final_episode_redownload_if_ready(s, download_id)
            s.commit()
            continue
        active_operation_id = active.id if active is not None else None

        # cancel_operation owns its own transaction. End this session's read
        # transaction first so SQLite never has to upgrade a stale snapshot.
        s.rollback()
        if active_operation_id is not None:
            try:
                cancel_operation(
                    active_operation_id,
                    reason=_CANCEL_REASON,
                    acknowledge=True,
                )
                canceled += 1
            except ValueError:
                # The operation may have reached terminal state between discovery
                # and cancellation. Durable intent below still closes that race.
                pass

        # For a queued/scheduled cancellation, the old run may already be
        # terminal now. For a RUNNING worker this deliberately remains a no-op
        # until its terminal callback consumes the same persistent intent.
        if queue_final_episode_redownload_if_ready(s, download_id):
            queued += 1
        s.commit()

    # Replacements whose prior attempt is already terminal can start now. A
    # canceled RUNNING attempt keeps the intent pending; its ordinary terminal
    # callback creates and dispatches the replacement after shutdown completes.
    dispatched = dispatch_queued_media_download_operations(s)
    s.commit()

    return TaskResult(
        summary=f"Queued {queued} final episode replacement(s)",
        data={
            "redownloads_queued": queued,
            "active_downloads_canceled": canceled,
            "redownloads_dispatched": dispatched,
        },
    )
