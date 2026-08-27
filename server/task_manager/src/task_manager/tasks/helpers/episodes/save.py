from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from backend.api.helpers import update_database_fields, create_database_fields
from backend.db.models import Show, Season
from backend.db.models.media_item import Episode
from backend.types.episode_types import EpisodePublishStatus
from backend.utils.helpers import generate_uuid
from backend.types.media_types import MediaType

from dailywire_api.dw_api.client import MiddlewareClient
from dailywire_api.records import DwEpisodeRecord
from .identifier import EpisodeWithIdentifier
from .status import is_published_final, get_publish_status_from_dw_detail


@dataclass
class SavedEpisode:
    """The outcome of persisting one remote episode."""
    episode: Episode
    status: EpisodePublishStatus
    # True when the status was resolved from the DW detail endpoint (the same path
    # ``monitor_episode_worker`` uses); False for cheap list-heuristic final episodes.
    detail_resolved: bool


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


def _resolve_and_upsert_episode(
        s: Session,
        *,
        show: Show,
        season: Season,
        client: MiddlewareClient,
        require_member_exclusive: bool,
        ep_id: str,
        ep: DwEpisodeRecord,
        index_value: int,
) -> SavedEpisode:
    """Persist one episode with the status it currently holds on Daily Wire.

    Episodes the cheap list heuristic already considers final are saved as
    ``PUBLISHED_FINAL`` without an extra request (the back catalog). Everything else
    is resolved through the detail endpoint exactly like ``monitor_episode_worker``,
    so a freshly-indexed episode carries its real non-final status.
    """
    if is_published_final(ep):
        status = EpisodePublishStatus.PUBLISHED_FINAL
        record: DwEpisodeRecord = ep
        detail_resolved = False
    else:
        record = client.get_episode_details(
            ep.slug,
            require_member_exclusive=require_member_exclusive,
        )
        status = get_publish_status_from_dw_detail(record)
        detail_resolved = True

    ep_to_save = record.model_copy(
        update={"publish_status": status.value},
        deep=True,
    )
    episode = upsert_episode(
        s,
        show=show,
        season=season,
        ep=ep_to_save,
        index_value=index_value,
        ep_id=ep_id,
    )
    return SavedEpisode(episode=episode, status=status, detail_resolved=detail_resolved)


def save_dw_episodes_per_season_desc(s: Session, *,
                                     show: Show,
                                     season: Season,
                                     episodes: list[EpisodeWithIdentifier],
                                     start_index: int,
                                     client: MiddlewareClient,
                                     require_member_exclusive: bool) -> tuple[int, list[SavedEpisode]]:
    """
    Index a single season within its own transaction scope. On error, roll back
    all changes for the season and re-raise.

    Returns the next index to use for subsequent (older) episodes together with the
    episodes that were saved.
    """
    current_index = start_index
    saved: list[SavedEpisode] = []

    try:
        for ep_id, ep in episodes:
            saved.append(_resolve_and_upsert_episode(
                s,
                show=show,
                season=season,
                client=client,
                require_member_exclusive=require_member_exclusive,
                ep_id=ep_id,
                ep=ep,
                index_value=current_index,
            ))
            current_index -= 1

        # Commit this season
        s.commit()
        return current_index, saved
    except Exception:
        s.rollback()
        raise


def save_dw_episodes_per_season_asc(s: Session, *,
                                    show: Show,
                                    season: Season,
                                    episodes: list[EpisodeWithIdentifier],
                                    start_index: int,
                                    client: MiddlewareClient,
                                    require_member_exclusive: bool) -> tuple[int, list[SavedEpisode]]:
    """
    Index a single season within its own transaction scope. On error, roll back
    all changes for the season and re-raise.

    Returns the next index to use for subsequent (newer) episodes together with the
    episodes that were saved.
    """
    current_index = start_index
    saved: list[SavedEpisode] = []

    try:
        for ep_id, ep in episodes:
            saved.append(_resolve_and_upsert_episode(
                s,
                show=show,
                season=season,
                client=client,
                require_member_exclusive=require_member_exclusive,
                ep_id=ep_id,
                ep=ep,
                index_value=current_index,
            ))
            current_index += 1

        # Commit this season
        s.commit()
        return current_index, saved
    except Exception:
        s.rollback()
        raise
