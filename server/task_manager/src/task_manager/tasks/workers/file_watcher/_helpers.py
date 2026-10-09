from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Optional

from sqlalchemy import func, select
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


def _download_root_path_prefix(download_root: Path) -> str:
    return f"{download_root}{os.sep}"


def _scoped_download_count(s: Session, stmt) -> int:
    return int(s.scalar(
        select(func.count()).select_from(stmt.order_by(None).subquery())
    ) or 0)


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

    download_root = Path(
        get_settings().download_settings.download_root
    ).expanduser().absolute()
    try:
        root_is_available = download_root.is_dir()
    except OSError:
        root_is_available = False

    if not root_is_available:
        skipped = _scoped_download_count(s, stmt)
        if skipped:
            logger.warning(
                "file_watcher: configured download root '%s' is unavailable; skipped %s artifact(s) and left their database state unchanged",
                download_root,
                skipped,
            )
        return []

    root_filter = MediaDownloadBase.file_path.startswith(
        _download_root_path_prefix(download_root),
        autoescape=True,
    )
    skipped = _scoped_download_count(s, stmt.where(~root_filter))
    if skipped:
        logger.warning(
            "file_watcher: skipped %s artifact(s) whose recorded paths are outside the configured download root '%s'; leaving their database state unchanged",
            skipped,
            download_root,
        )

    return list(s.scalars(
        stmt.where(root_filter).order_by(MediaDownloadBase.id)
    ))
