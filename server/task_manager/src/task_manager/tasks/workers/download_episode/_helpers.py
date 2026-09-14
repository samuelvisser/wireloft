from __future__ import annotations

from sqlalchemy.orm import Session

from backend.db.models import Episode, Show
from backend.types.dailywire_user_info import WlDwMembershipLevel
from dailywire_api.dw_api.client import MiddlewareClient
from dailywire_downloader import DownloadCancelled


def refresh_episode_media_urls(s: Session, *, episode: Episode, show: Show) -> None:
    """Fetch fresh episode media URLs without retaining a DB transaction during HTTP I/O."""
    episode_id = episode.id
    episode_slug = episode.slug
    require_member_exclusive = show.membership_level != WlDwMembershipLevel.FREE.value

    s.rollback()
    detail = MiddlewareClient().get_episode_details(
        episode_slug,
        require_member_exclusive=require_member_exclusive,
    )

    episode = s.get(Episode, episode_id)
    if episode is None:
        raise DownloadCancelled(f"Episode {episode_id} was deleted while refreshing media URLs")
    episode.video_url = detail.video_url
    episode.audio_url = detail.audio_url
    s.commit()
