from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models.media_download import MediaDownloadAttempt, MediaDownloadBase
from backend.types.download_profile_types import MediaDownloadStatus
from task_manager.tasks.helpers.progress import update_progress
from task_manager.tasks.workers.download_profile_worker._helpers import trigger_next_pending_downloads

_INTERRUPTED_MESSAGE = "Interrupted: WireLoft was restarted while this download was in progress"


async def run_resume_interrupted_downloads(s: Session, *, progress=None) -> None:
    """Requeue any download still marked DOWNLOADING from before this startup.

    A row can only legitimately be DOWNLOADING while a worker in *this*
    process is actively running it. On a fresh app startup nothing has
    started a download yet, so any row still in that state was orphaned by
    an unclean shutdown (the process was killed mid-download) - it would
    otherwise stay stuck there forever. Worse, it keeps counting against the
    concurrency budget (see download_profile_worker.remaining_download_budget),
    silently capping every future sweep short and blocking the whole queue
    from ever moving on to newer downloads.
    """
    stuck = list(
        s.execute(
            select(MediaDownloadBase).where(MediaDownloadBase.download_status == MediaDownloadStatus.DOWNLOADING.value)
        ).scalars()
    )

    if not stuck:
        update_progress(progress, 100, "No interrupted downloads to resume")
        print("resume_interrupted_downloads completed: nothing to do")
        return

    now = datetime.now(timezone.utc)
    for download in stuck:
        # Record what we know as a terminal ledger entry before resetting the
        # row, so the interruption is visible in the download's log instead
        # of silently vanishing the moment it's requeued.
        s.add(MediaDownloadAttempt(
            media_download_id=download.id,
            is_redownload=bool(getattr(download, "is_redownload_attempt", False) or False),
            status=MediaDownloadStatus.ERROR.value,
            error_message=_INTERRUPTED_MESSAGE,
            downloaded_bytes=download.downloaded_bytes,
            format_downloaded=download.format_downloaded,
            started_at=download.started_at,
            finished_at=now,
        ))

        download.attempt_generation += 1
        download.download_status = MediaDownloadStatus.PENDING.value
        download.progress = 0
        download.error_message = None
        download.downloaded_bytes = None
        download.format_downloaded = None
        download.started_at = None
        download.finished_at = None
    s.commit()

    triggered = trigger_next_pending_downloads(s)
    message = f"Resumed {len(stuck)} interrupted download(s); queued {triggered} for retry"
    update_progress(progress, 100, message)
    print(f"resume_interrupted_downloads completed: {message}")
