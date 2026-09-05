from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Episode, Show
from backend.db.models.media_download import MediaDownloadBase
from backend.types.download_profile_types import MediaDownloadArtifactStatus

# Persistent artifacts whose path should exist on disk. Previously flagged
# artifacts stay in scope so they can be reconciled back to healthy.
TRACKED_ARTIFACT_STATUSES = (
    MediaDownloadArtifactStatus.AVAILABLE.value,
    MediaDownloadArtifactStatus.MISSING.value,
    MediaDownloadArtifactStatus.CORRUPTED.value,
)


def get_tracked_downloads(s: Session, *, show_id: Optional[int], show_slug: Optional[str]) -> list[MediaDownloadBase]:
    """All persistent MediaDownload artifacts that should currently have a file."""
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
        stmt = stmt.join(Episode, Episode.id == MediaDownloadBase.media_item_id).where(Episode.show_id == show_id)

    return list(s.execute(stmt.order_by(MediaDownloadBase.id)).scalars())
