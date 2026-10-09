from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.db.datetime_types import utc_datetime
from backend.db.models import Episode
from backend.types.episode_types import EpisodePublishStatus
from backend.utils.episode_publication_timing import best_effort_published_date
from config import get_settings


def episode_download_delay_ready_at(episode: Episode) -> datetime | None:
    """Return when WireLoft's configured post-publication download delay expires."""
    settings = get_settings().download_settings
    delay_minutes = settings.episode_download_delay_minutes
    if delay_minutes <= 0:
        return None

    publication_time: datetime | None
    if episode.publish_status == EpisodePublishStatus.PUBLISHED_FINAL:
        if settings.ensure_safe_delay:
            publication_time = (
                episode.safe_published_final
                or episode.recorded_published_final
            )
            if publication_time is None:
                # For episodes added during an initial index
                publication_time = best_effort_published_date(episode)
        else:
            publication_time = best_effort_published_date(episode)
    elif episode.publish_status == EpisodePublishStatus.PUBLISHED_WITH_COUNTDOWN:
        publication_time = episode.safe_live_ended
        if publication_time is None and episode.published_date is not None:
            publication_time = utc_datetime(episode.published_date)
    else:
        publication_time = None

    if publication_time is None:
        return None
    return utc_datetime(publication_time) + timedelta(minutes=delay_minutes)


def episode_download_delay_passed(
        episode: Episode,
        *,
        now: datetime | None = None,
) -> bool:
    """Return whether the configured post-publication download delay has elapsed."""
    ready_at = episode_download_delay_ready_at(episode)
    if ready_at is None:
        return True
    current = utc_datetime(now or datetime.now(timezone.utc))
    return ready_at <= current
