from __future__ import annotations

import logging
import os
from typing import Optional

from sqlalchemy.orm import Session

from backend.db.models.media_download import MediaDownloadBase
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from config import get_settings

from ._helpers import get_tracked_downloads

logger = logging.getLogger(__name__)

_HEALTHY_STATUS = MediaDownloadArtifactStatus.AVAILABLE.value
_PROBLEM_STATUSES = (
    MediaDownloadArtifactStatus.MISSING.value,
    MediaDownloadArtifactStatus.CORRUPTED.value,
)
_MIN_SIZE_RATIO = 0.5


async def run_file_watcher(s: Session, *, show_id: Optional[int] = None, show_slug: Optional[str] = None, progress=None) -> None:
    """Reconcile persistent MediaDownload artifact facts with the filesystem.

    This worker never changes execution state. A missing/corrupt file is normal
    domain state; whether a replacement is currently queued or running remains a
    TaskOperation/TaskRun concern.
    """
    settings = get_settings().file_watcher
    if not settings.enabled:
        print("file_watcher is disabled (file_watcher.enabled=false), skipping")
        return

    print("Starting file_watcher")
    downloads = get_tracked_downloads(s, show_id=show_id, show_slug=show_slug)
    updated = 0
    for download in downloads:
        if _reconcile(download, verify_file_size=settings.verify_file_size):
            updated += 1

    s.commit()
    print(f"file_watcher completed: checked {len(downloads)} artifact(s), updated {updated}")


def _reconcile(download: MediaDownloadBase, *, verify_file_size: bool) -> bool:
    problem = _detect_problem(download, verify_file_size=verify_file_size)

    if problem is not None:
        status, message = problem
        if download.artifact_status == status.value and download.artifact_error == message:
            return False
        logger.warning("file_watcher: media_download %s -> %s (%s)", download.id, status.value, message)
        download.artifact_status = status.value
        download.artifact_error = message
        return True

    if download.artifact_status in _PROBLEM_STATUSES:
        logger.info("file_watcher: media_download %s file is healthy again", download.id)
        download.artifact_status = _HEALTHY_STATUS
        download.artifact_error = None
        return True

    return False


def _detect_problem(
    download: MediaDownloadBase,
    *,
    verify_file_size: bool,
) -> Optional[tuple[MediaDownloadArtifactStatus, str]]:
    path = download.file_path

    try:
        exists = os.path.exists(path)
    except OSError as exc:
        return MediaDownloadArtifactStatus.MISSING, f"Could not check '{path}': {exc}"

    if not exists:
        return MediaDownloadArtifactStatus.MISSING, f"File not found at '{path}'"
    if not os.path.isfile(path):
        return MediaDownloadArtifactStatus.CORRUPTED, f"Expected a file at '{path}' but found something else"

    try:
        size = os.path.getsize(path)
    except OSError as exc:
        return MediaDownloadArtifactStatus.MISSING, f"Could not read '{path}': {exc}"

    if size == 0:
        return MediaDownloadArtifactStatus.CORRUPTED, f"File at '{path}' is empty"

    if verify_file_size and download.downloaded_bytes and size < download.downloaded_bytes * _MIN_SIZE_RATIO:
        return MediaDownloadArtifactStatus.CORRUPTED, (
            f"File at '{path}' is only {size} bytes, well under the "
            f"{download.downloaded_bytes} recorded when it finished downloading"
        )

    return None
