from __future__ import annotations

import logging
import os
from typing import Optional

from sqlalchemy.orm import Session

from backend.db.models.media_download import MediaDownloadBase
from backend.types.download_profile_types import MediaDownloadStatus
from config import get_settings

from ._helpers import get_tracked_downloads

logger = logging.getLogger(__name__)

# The status a download is restored to once its file is healthy again.
_HEALTHY_STATUS = MediaDownloadStatus.DOWNLOADED.value
_PROBLEM_STATUSES = (MediaDownloadStatus.MISSING.value, MediaDownloadStatus.CORRUPTED.value)


async def run_file_watcher(s: Session, *, show_id: Optional[int] = None, show_slug: Optional[str] = None, progress=None) -> None:
    """Reconcile media_downloads rows with what is actually on disk.

    A download whose file was deleted or renamed/moved away is flagged
    'missing'; one whose file is empty, or has shrunk below the size recorded
    when it finished downloading, is flagged 'corrupted'. A previously
    flagged download whose file is healthy again is put back to 'downloaded'.
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
    print(f"file_watcher completed: checked {len(downloads)} download(s), updated {updated}")


def _reconcile(download: MediaDownloadBase, *, verify_file_size: bool) -> bool:
    """Compare one download's file against disk and fix up its status if it drifted.

    Returns True when the row's status/error_message changed.
    """
    problem = _detect_problem(download, verify_file_size=verify_file_size)

    if problem is not None:
        status, message = problem
        if download.download_status == status.value and download.error_message == message:
            return False
        logger.warning("file_watcher: media_download %s -> %s (%s)", download.id, status.value, message)
        download.download_status = status.value
        download.error_message = message
        return True

    if download.download_status in _PROBLEM_STATUSES:
        logger.info("file_watcher: media_download %s file is healthy again, marking downloaded", download.id)
        download.download_status = _HEALTHY_STATUS
        download.error_message = None
        return True

    return False


def _detect_problem(download: MediaDownloadBase, *, verify_file_size: bool) -> Optional[tuple[MediaDownloadStatus, str]]:
    """Inspect a download's file on disk; return the problem found, if any."""
    path = download.file_path

    try:
        exists = os.path.exists(path)
    except OSError as e:
        return MediaDownloadStatus.MISSING, f"Could not check '{path}': {e}"

    if not exists:
        return MediaDownloadStatus.MISSING, f"File not found at '{path}'"
    if not os.path.isfile(path):
        return MediaDownloadStatus.CORRUPTED, f"Expected a file at '{path}' but found something else"

    try:
        size = os.path.getsize(path)
    except OSError as e:
        return MediaDownloadStatus.MISSING, f"Could not read '{path}': {e}"

    if size == 0:
        return MediaDownloadStatus.CORRUPTED, f"File at '{path}' is empty"

    if verify_file_size and download.downloaded_bytes and size < download.downloaded_bytes:
        shortfall = download.downloaded_bytes - size
        return MediaDownloadStatus.CORRUPTED, (
            f"File at '{path}' is {shortfall} bytes smaller than the "
            f"{download.downloaded_bytes} recorded when it finished downloading"
        )

    return None
