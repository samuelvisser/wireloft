from __future__ import annotations

from dataclasses import dataclass
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


@dataclass(frozen=True)
class TrackedDownloadSnapshot:
    """Detached filesystem-relevant facts for one persistent artifact."""

    id: int
    file_path: str
    artifact_status: str
    artifact_error: Optional[str]
    downloaded_bytes: Optional[int]
    artifact_stat_dev: Optional[str]
    artifact_stat_ino: Optional[str]
    artifact_size_bytes: Optional[int]
    artifact_fingerprint: Optional[str]


def get_tracked_downloads(
    s: Session,
    *,
    show_id: Optional[int],
    show_slug: Optional[str],
) -> list[TrackedDownloadSnapshot]:
    """Snapshot persistent artifacts that should currently have a file."""
    stmt = select(
        MediaDownloadBase.id,
        MediaDownloadBase.file_path,
        MediaDownloadBase.artifact_status,
        MediaDownloadBase.artifact_error,
        MediaDownloadBase.downloaded_bytes,
        MediaDownloadBase.artifact_stat_dev,
        MediaDownloadBase.artifact_stat_ino,
        MediaDownloadBase.artifact_size_bytes,
        MediaDownloadBase.artifact_fingerprint,
    ).where(MediaDownloadBase.artifact_status.in_(TRACKED_ARTIFACT_STATUSES))

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

    rows = s.execute(stmt.order_by(MediaDownloadBase.id)).mappings().all()
    return [
        TrackedDownloadSnapshot(
            id=row["id"],
            file_path=row["file_path"],
            artifact_status=row["artifact_status"],
            artifact_error=row["artifact_error"],
            downloaded_bytes=row["downloaded_bytes"],
            artifact_stat_dev=row["artifact_stat_dev"],
            artifact_stat_ino=row["artifact_stat_ino"],
            artifact_size_bytes=row["artifact_size_bytes"],
            artifact_fingerprint=row["artifact_fingerprint"],
        )
        for row in rows
    ]
