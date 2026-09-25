from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Episode
from backend.db.models.media_download import EpisodeMediaDownload
from backend.types.episode_types import EpisodePublishStatus
from task_manager.scheduler.operation_control import cancel_operation
from task_manager.scheduler.results import TaskResult
from task_manager.scheduler.types import OperationSource
from task_manager.tasks.media_download_operations import (
    create_media_download_operation,
    dispatch_queued_media_download_operations,
    get_active_media_download_operation,
    prepare_media_download_artifact,
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
            and active.context.get("episode_publish_status") == EpisodePublishStatus.PUBLISHED_FINAL.value
        ):
            # A fresh attempt created after final publication already satisfies
            # the replacement intent; do not cancel it as if it were countdown work.
            download.redownload_when_final = False
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
                # The attempt may have become terminal between discovery and the
                # cancellation call. Reconciliation below handles that state.
                pass

        download = s.get(EpisodeMediaDownload, download_id)
        if download is None or not download.redownload_when_final:
            s.rollback()
            continue

        episode = s.get(Episode, download.media_item_id)
        if episode is None or episode.publish_status != EpisodePublishStatus.PUBLISHED_FINAL.value:
            s.rollback()
            continue

        # A concurrent explicit retry after final publication already satisfies
        # the intent. Do not replace that fresh operation with another one.
        replacement = get_active_media_download_operation(s, download.id)
        if replacement is not None:
            download.redownload_when_final = False
            s.commit()
            continue

        prepare_media_download_artifact(s, download)
        download.redownload_when_final = False
        create_media_download_operation(
            s,
            download,
            source=OperationSource.SYSTEM.value,
            is_redownload=True,
        )
        s.commit()
        queued += 1

    # A canceled RUNNING task continues holding its concurrency slot until it
    # reaches a cooperative cancellation checkpoint. The replacement remains
    # durably queued and this dispatcher starts it immediately when a slot is
    # already free; the ordinary terminal callback fills the lane otherwise.
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
