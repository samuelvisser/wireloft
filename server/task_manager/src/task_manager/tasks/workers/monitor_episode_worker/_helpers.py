from __future__ import annotations

from sqlalchemy.orm import Session

from backend.db.models import Episode
from backend.types.episode_types import EpisodePublishStatus
from dailywire_api.records import DwEpisodeDetailRecord


def save_status_metadata(
        s: Session,
        *,
        episode: Episode,
        dw_episode: DwEpisodeDetailRecord,
        status: EpisodePublishStatus,
) -> None:
    """Keep phase-specific remote slugs without making them record identity."""
    match status:
        case EpisodePublishStatus.SCHEDULED | EpisodePublishStatus.LIVE:
            episode.set_meta("ep_status.live.slug", dw_episode.slug)
            episode.set_meta(
                "ep_status.live.sharing_url",
                dw_episode.sharing_url,
            )
        case EpisodePublishStatus.DELAYED:
            episode.set_meta("ep_status.delayed.slug", dw_episode.slug)
        case EpisodePublishStatus.DW_PROCESSING:
            episode.set_meta(
                "ep_status.dw_processing.slug",
                dw_episode.slug,
            )
        case (
            EpisodePublishStatus.PUBLISHED_WITH_COUNTDOWN
            | EpisodePublishStatus.PUBLISHED_FINAL
        ):
            pass

    s.flush()
