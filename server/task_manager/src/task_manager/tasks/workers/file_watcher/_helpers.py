from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Episode, Show
from backend.db.models.media_download import MediaDownloadBase
from backend.types.download_profile_types import MediaDownloadArtifactStatus
from config import get_settings


logger = logging.getLogger(__name__)

# Persistent artifacts whose path should exist on disk. Previously flagged
# artifacts stay in scope so they can be reconciled back to healthy.
TRACKED_ARTIFACT_STATUSES = (
    MediaDownloadArtifactStatus.AVAILABLE.value,
    MediaDownloadArtifactStatus.MISSING.value,
    MediaDownloadArtifactStatus.CORRUPTED.value,
)


def _inside_current_download_root(path: str, download_root: Path) -> bool:
    """Use lexical absolute paths so this check never waits on a remote filesystem."""
    try:
        return Path(path).expanduser().absolute().is_relative_to(download_root)
    except (OSError, RuntimeError, ValueError):
        return False


def _filter_current_download_root(
    downloads: list[MediaDownloadBase],
) -> list[MediaDownloadBase]:
    """Limit reconciliation to artifacts visible through this WireLoft filesystem.

    WireLoft output templates are rooted under ``downloadSettings.downloadRoot``.
    A copied database can therefore contain valid artifact records whose absolute
    paths belong to another host. Those foreign paths must not be converted to
    ``missing`` merely because this WireLoft instance cannot see that filesystem.

    Likewise, if the configured download root itself is unavailable, there is no
    trustworthy filesystem view from which to conclude that individual media files
    disappeared. Skip the scan and preserve the database state until the root is
    available again.
    """
    if not downloads:
        return downloads

    download_root = Path(
        get_settings().download_settings.download_root
    ).expanduser().absolute()
    try:
        root_is_available = download_root.is_dir()
    except OSError:
        root_is_available = False
    if not root_is_available:
        logger.warning(
            "file_watcher: configured download root '%s' is unavailable; skipped %s artifact(s) and left their database state unchanged",
            download_root,
            len(downloads),
        )
        return []

    current = [
        download
        for download in downloads
        if _inside_current_download_root(download.file_path, download_root)
    ]
    skipped = len(downloads) - len(current)
    if skipped:
        logger.warning(
            "file_watcher: skipped %s artifact(s) whose recorded paths are outside the configured download root '%s'; leaving their database state unchanged",
            skipped,
            download_root,
        )
    return current


def get_tracked_downloads(
    s: Session,
    *,
    show_id: Optional[int],
    show_slug: Optional[str],
) -> list[MediaDownloadBase]:
    """Load persistent artifacts that should currently have a file."""
    stmt = select(MediaDownloadBase).where(
        MediaDownloadBase.artifact_status.in_(TRACKED_ARTIFACT_STATUSES)
    )

    if show_slug:
        stmt = (
            stmt.join(Episode, Episode.id == MediaDownloadBase.media_item_id)
            .join(Show, Show.id == Episode.show_id)
            .where(Show.slug == show_slug)
        )
    elif show_id:
        stmt = stmt.join(Episode, Episode.id == MediaDownloadBase.media_item_id).where(
            Episode.show_id == show_id
        )

    downloads = list(s.execute(stmt.order_by(MediaDownloadBase.id)).scalars())
    return _filter_current_download_root(downloads)
