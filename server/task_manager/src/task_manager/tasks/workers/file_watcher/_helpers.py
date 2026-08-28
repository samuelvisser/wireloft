from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Episode, Show
from backend.db.models.media_download import MediaDownloadBase
from backend.types.download_profile_types import MediaDownloadStatus

# Downloads whose file is expected to exist on disk right now. A previously
# flagged download stays in scope so it can be reconciled back to healthy.
TRACKED_STATUSES = (
    MediaDownloadStatus.DOWNLOADED.value,
    MediaDownloadStatus.REDOWNLOADED.value,
    MediaDownloadStatus.MISSING.value,
    MediaDownloadStatus.CORRUPTED.value,
)


def get_tracked_downloads(s: Session, *, show_id: Optional[int], show_slug: Optional[str]) -> list[MediaDownloadBase]:
    """All media downloads that should currently have a file on disk.

    ``show_id``/``show_slug`` narrow the scan to one show's episodes.
    ``show_id=0`` (the scheduler's "global" resource id) and ``None`` both
    mean "every show", matching the convention used by the other workers.
    """
    stmt = select(MediaDownloadBase).where(MediaDownloadBase.download_status.in_(TRACKED_STATUSES))

    if show_slug:
        stmt = (
            stmt.join(Episode, Episode.id == MediaDownloadBase.media_item_id)
            .join(Show, Show.id == Episode.show_id)
            .where(Show.slug == show_slug)
        )
    elif show_id:
        stmt = stmt.join(Episode, Episode.id == MediaDownloadBase.media_item_id).where(Episode.show_id == show_id)

    return list(s.execute(stmt.order_by(MediaDownloadBase.id)).scalars())
