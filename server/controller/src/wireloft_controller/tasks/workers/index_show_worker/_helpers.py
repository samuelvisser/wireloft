from __future__ import annotations

from typing import Optional, Sequence, Dict, Tuple, Any

from sqlalchemy import select

from backend.api.helpers import update_database_fields, create_database_fields
from backend.db.core import get_session
from backend.db.models import Show, Season
from backend.db.models.media_item import Episode
from backend.utils.helpers import generate_uuid
from backend.types.media_types import MediaType

from dailywire_api.records import EpisodeRecord

from wireloft_controller.tasks.helpers.episodes import is_published_final



def count_total_episodes(episodes_map: Dict[int, list[Any]]) -> int:
    """
    Count all episodes by counting the items in the map.
    """
    count = 0
    for _, eps in episodes_map.items():
        count += len(eps)

    return count


def get_seasons_sorted_desc(show_slug: str) -> Sequence[Season]:
    """Get seasons for a show from the DB sorted by Season.index descending."""
    s = get_session()
    try:
        return s.scalars(
            select(Season)
            .filter(Season.show.has(slug=show_slug))
            .order_by(Season.index.desc())
        ).all()
    finally:
        s.close()


def upsert_episode(
        s, *, show: Show, season: Season, ep: EpisodeRecord, index_value: int, ep_id: str
) -> Episode:
    """Create or update a single Episode row for the given EpisodeRecord."""

    # Check if the episode already exists in DB
    episode: Optional[Episode] = (
        s.query(Episode)
        .filter(Episode.show_id == show.id, Episode.dw_id == ep.dw_id)
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


def index_one_season(s, *,
                     show: Show,
                     season: Season,
                     episodes: list[Tuple[str, EpisodeRecord]],
                     start_index: int,
                     ) -> int:
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

            upsert_episode(s, show=show, season=season, ep=ep, index_value=current_index, ep_id=ep_id)
            current_index -= 1

        # Commit this season
        s.commit()
        return current_index
    except Exception:
        s.rollback()
        raise
