from __future__ import annotations

from sqlalchemy.orm import Session

from backend.db.models.media_download import EpisodeMediaDownload
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from task_manager.scheduler.operation_control import cancel_operation
from task_manager.tasks.media_download_operations import (
    get_active_media_download_operation,
    prepare_media_download_artifact,
)
from task_manager.tasks.workers.file_watcher.service import resolve_media_download_file


def cancel_active_download_attempts(
        s: Session,
        downloads: list[EpisodeMediaDownload] | tuple[EpisodeMediaDownload, ...],
        *,
        reason: str,
        source: str | None = None,
) -> None:
    """Cancel matching active media.download operations before destructive artifact changes."""
    operation_ids = {
        active.id
        for download in downloads
        for active in (get_active_media_download_operation(s, download.id),)
        if active is not None and (source is None or active.source == source)
    }

    # cancel_operation owns its own short transaction. Drop this session's read
    # transaction first so SQLite never has to upgrade an old snapshot afterwards.
    s.rollback()
    for operation_id in operation_ids:
        try:
            cancel_operation(operation_id, reason=reason, acknowledge=True)
        except ValueError:
            pass
    s.expire_all()


def delete_episode_download_artifact(
        s: Session,
        download: EpisodeMediaDownload,
) -> None:
    """Remove one episode artifact through the canonical MediaDownload lifecycle."""
    if download.artifact_status != MediaDownloadArtifactStatus.ABSENT.value:
        resolve_media_download_file(
            s,
            download,
            release_read_transaction=True,
        )
    prepare_media_download_artifact(s, download)
    s.flush()
