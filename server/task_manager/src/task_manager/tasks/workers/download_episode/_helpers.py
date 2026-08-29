from __future__ import annotations

from typing import Optional, Sequence

from sqlalchemy import update
from sqlalchemy.orm import Session

from backend.db.core import get_session
from backend.db.models import Episode, Show
from backend.db.models.media_download import MediaDownloadBase
from backend.types.dailywire_user_info import WlDwMembershipLevel
from backend.types.local_media_profile_types import PreferredFormat
from dailywire_api.dw_api.client import MiddlewareClient
from dailywire_downloader import DownloadProgress, MediaUnavailableError, VideoRendition

# Requested video height per preferred format; audio-only is handled separately
FORMAT_HEIGHTS: dict[str, int] = {
    PreferredFormat.FORMAT_4K.value: 2160,
    PreferredFormat.FORMAT_1080P.value: 1080,
    PreferredFormat.FORMAT_720P.value: 720,
}


def select_rendition(renditions: Sequence[VideoRendition], requested_height: int) -> VideoRendition:
    """Pick the rendition that best honors the requested height.

    No conversion is ever done: prefer the smallest rendition that is at least
    the requested height; when nothing reaches it, take the highest available.
    Equal heights are broken by the higher bandwidth (better quality encode).
    """
    with_height = [r for r in renditions if r.height]
    if not with_height:
        raise MediaUnavailableError("Master playlist offers no video renditions with a resolution")

    at_least = [r for r in with_height if r.height >= requested_height]
    if at_least:
        return min(at_least, key=lambda r: (r.height, -(r.bandwidth or 0)))
    return max(with_height, key=lambda r: (r.height, r.bandwidth or 0))


def refresh_episode_media_urls(s: Session, *, episode: Episode, show: Show) -> None:
    """Fetch fresh media URLs from the Daily Wire API and persist them."""
    client = MiddlewareClient()
    detail = client.get_episode_details(
        episode.slug,
        require_member_exclusive=(show.membership_level != WlDwMembershipLevel.FREE.value),
    )
    episode.video_url = detail.video_url
    episode.audio_url = detail.audio_url
    s.commit()


class RowProgressWriter:
    """Persists download progress onto the media_downloads row (and TaskRun).

    Uses a throwaway session per write so it never interferes with the worker's
    main transaction; the downloader already throttles callbacks to ~1/second.
    """

    def __init__(
            self,
            media_download_id: int,
            task_progress=None,
            attempt_generation: Optional[int] = None,
    ):
        self._id = media_download_id
        self._task_progress = task_progress
        self._attempt_generation = attempt_generation
        self._last_pct: int = -1

    def __call__(self, p: DownloadProgress) -> None:
        fraction = p.fraction
        if fraction is None:
            return
        pct = max(0, min(99, int(fraction * 100)))
        if pct == self._last_pct:
            return
        self._last_pct = pct

        updated = self.write(pct, downloaded_bytes=p.bytes_downloaded)
        if updated and self._task_progress is not None:
            self._task_progress.set(pct)

    def write(self, pct: int, *, downloaded_bytes: Optional[int] = None) -> bool:
        values: dict = {"progress": pct}
        if downloaded_bytes is not None:
            values["downloaded_bytes"] = downloaded_bytes

        s = get_session()
        try:
            stmt = update(MediaDownloadBase).where(MediaDownloadBase.id == self._id)
            if self._attempt_generation is not None:
                stmt = stmt.where(
                    MediaDownloadBase.attempt_generation == self._attempt_generation
                )
            result = s.execute(stmt.values(**values))
            s.commit()
            return bool(result.rowcount)
        except Exception:
            s.rollback()
            return False
        finally:
            s.close()
