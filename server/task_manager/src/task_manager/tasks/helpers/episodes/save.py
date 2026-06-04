from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from backend.api.helpers import update_database_fields, create_database_fields
from backend.db.models import Show, Season
from backend.db.models.media_item import Episode
from backend.types.episode_types import EpisodePublishStatus
from backend.utils.helpers import generate_uuid
from backend.types.media_types import MediaType

from dailywire_api.records import DwEpisodeRecord
from .mapper import EpisodeWithIdentifier
from .status import is_published_final, get_publish_status_from_dw_detail


def upsert_episode(
        s, *, show: Show, season: Season, ep: DwEpisodeRecord, index_value: int, ep_id: str
) -> Episode:
    """Create or update a single Episode row for the given EpisodeRecord."""

    # Check if the episode already exists in DB
    episode: Optional[Episode] = (
        s.query(Episode)
        .filter(Episode.show_id == show.id, Episode.slug == ep.slug)
        .one_or_none()
    )

    if episode is None:
        # Create new (only pass fields that exist on the SQLAlchemy model)
        episode = create_database_fields(Episode, data={
            **ep.model_dump(mode="python", by_alias=False),
            **{
                "uuid": generate_uuid(),
                "type": MediaType.EPISODE.value,
                "show_id": show.id,
                "season_id": season.id,
                "index": index_value,
                "episode_identifier": ep_id,
            }
        })
        s.add(episode)
    else:
        # Update existing in place and reindex
        update_database_fields(episode, ep, ignore_extra_fields=True)
        episode.season_id = season.id
        episode.index = index_value
        episode.episode_identifier = ep_id

    s.flush()
    return episode


def save_dw_episodes_per_season_desc(s: Session, *,
                                     show: Show,
                                     season: Season,
                                     episodes: list[EpisodeWithIdentifier],
                                     start_index: int) -> int:
    """
    Index a single season within its own transaction scope. On error, roll back
    all changes for the season and re-raise.

    Returns the next index to use for subsequent (older) episodes.
    """
    current_index = start_index

    try:
        for ep_id, ep in episodes:
            if not is_published_final(ep):
                current_index -= 1
                continue

            ep_new = ep.model_copy(update={
                "publish_status": EpisodePublishStatus.PUBLISHED_FINAL.value
            }, deep=True)

            upsert_episode(s, show=show, season=season, ep=ep_new, index_value=current_index, ep_id=ep_id)
            current_index -= 1

        # Commit this season
        s.commit()
        return current_index
    except Exception:
        s.rollback()
        raise


def save_dw_episodes_per_season_asc(s: Session, *,
                                    show: Show,
                                    season: Season,
                                    episodes: list[EpisodeWithIdentifier],
                                    start_index: int) -> int:
    """
    Index a single season within its own transaction scope. On error, roll back
    all changes for the season and re-raise.

    Returns the next index to use for subsequent (older) episodes.
    """
    current_index = start_index

    try:
        for ep_id, ep in episodes:
            if not is_published_final(ep):
                current_index += 1
                continue

            ep_new = ep.model_copy(update={
                "publish_status": EpisodePublishStatus.PUBLISHED_FINAL.value
            }, deep=True)

            upsert_episode(s, show=show, season=season, ep=ep_new, index_value=current_index, ep_id=ep_id)
            current_index += 1

        # Commit this season
        s.commit()
        return current_index
    except Exception:
        s.rollback()
        raise
