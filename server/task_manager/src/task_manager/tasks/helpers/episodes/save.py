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
from task_manager.events.transactional import queue_event
from .events import queue_episode_identifier_changed_event
from .identifier import EpisodeWithIdentifier
from .metadata import METADATA_REFRESH_REQUESTED_EVENT, metadata_is_final_for_new_episode
from .no_show import is_no_show_today_title
from .status import is_published_final, get_publish_status_from_dw_detail


@dataclass
class SavedEpisode:
    """The outcome of persisting one remote episode."""
    episode: Episode
    status: EpisodePublishStatus
    # True when the status was resolved from the DW detail endpoint (the same path
    # ``monitor_episode_worker`` uses); False for cheap list-heuristic final episodes.
    detail_resolved: bool


@dataclass(frozen=True)
class ResolvedEpisode:
    """An episode whose remote detail work is complete and is ready to persist."""
    episode_identifier: str
    record: DwEpisodeRecord
    status: EpisodePublishStatus
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
    was_created = episode is None
    old_episode_identifier = episode.episode_identifier if episode is not None else None

    if was_created:
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
                "is_no_show_today": is_no_show_today_title(ep.title),
                "metadata_is_final": metadata_is_final_for_new_episode(
                    ep.publish_status,
                    ep.published_date,
                ),
            }
        })
        s.add(episode)
    else:
        # Update existing in place and reindex
        update_database_fields(episode, ep, ignore_extra_fields=True)
        episode.season_id = season.id
        episode.index = index_value
        episode.episode_identifier = ep_id
        episode.is_no_show_today = is_no_show_today_title(ep.title)

    s.flush()

    if (
        not was_created
        and old_episode_identifier is not None
        and old_episode_identifier != episode.episode_identifier
    ):
        queue_episode_identifier_changed_event(
            s,
            episode=episode,
            show=show,
            old_identifier=old_episode_identifier,
        )

    # A newly discovered episode that is already final can skip the live monitor,
    # so explicitly ask the metadata worker to schedule its remaining checks.
    if (
        was_created
        and episode.publish_status == EpisodePublishStatus.PUBLISHED_FINAL.value
        and not episode.metadata_is_final
    ):
        queue_event(
            s,
            METADATA_REFRESH_REQUESTED_EVENT,
            {
                "resource_id": episode.id,
                "id": episode.id,
            },
        )

    return episode


def resolve_dw_episodes(
        *,
        episodes: list[EpisodeWithIdentifier],
        client: MiddlewareClient,
        require_member_exclusive: bool,
) -> list[ResolvedEpisode]:
    """Resolve every remote detail request before the database write phase.

    SQLite permits only one writer at a time. If a season starts flushing episode
    rows and then performs another Daily Wire HTTP request, that write transaction
    can block unrelated API writes for the entire request. Resolve all remote
    detail work first so the subsequent write transaction stays short.
    """
    resolved: list[ResolvedEpisode] = []
    for ep_id, ep in episodes:
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

        resolved.append(ResolvedEpisode(
            episode_identifier=ep_id,
            record=record,
            status=status,
            detail_resolved=detail_resolved,
        ))
    return resolved


def _upsert_resolved_episode(
        s: Session,
        *,
        show: Show,
        season: Season,
        resolved: ResolvedEpisode,
        index_value: int,
) -> SavedEpisode:
    ep_to_save = resolved.record.model_copy(
        update={"publish_status": resolved.status.value},
        deep=True,
    )
    episode = upsert_episode(
        s,
        show=show,
        season=season,
        ep=ep_to_save,
        index_value=index_value,
        ep_id=resolved.episode_identifier,
    )
    return SavedEpisode(
        episode=episode,
        status=resolved.status,
        detail_resolved=resolved.detail_resolved,
    )


def save_resolved_episodes_per_season_desc(
        s: Session, *,
        show: Show,
        season: Season,
        episodes: list[ResolvedEpisode],
        start_index: int,
) -> tuple[int, list[SavedEpisode]]:
    """Persist pre-resolved episodes newest-to-oldest within one transaction."""
    current_index = start_index
    saved: list[SavedEpisode] = []

    try:
        for resolved in episodes:
            saved.append(_upsert_resolved_episode(
                s,
                show=show,
                season=season,
                resolved=resolved,
                index_value=current_index,
            ))
            current_index -= 1

        s.commit()
        return current_index, saved
    except Exception:
        s.rollback()
        raise


def save_resolved_episodes_per_season_asc(
        s: Session, *,
        show: Show,
        season: Season,
        episodes: list[ResolvedEpisode],
        start_index: int,
) -> tuple[int, list[SavedEpisode]]:
    """Persist pre-resolved episodes oldest-to-newest within one transaction."""
    current_index = start_index
    saved: list[SavedEpisode] = []

    try:
        for resolved in episodes:
            saved.append(_upsert_resolved_episode(
                s,
                show=show,
                season=season,
                resolved=resolved,
                index_value=current_index,
            ))
            current_index += 1

        s.commit()
        return current_index, saved
    except Exception:
        s.rollback()
        raise


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

    Remote episode details are resolved before the first write so no database
    writer lock is held while waiting on Daily Wire.

    Returns the next index to use for subsequent (older) episodes together with the
    episodes that were saved.
    """
    try:
        resolved = resolve_dw_episodes(
            episodes=episodes,
            client=client,
            require_member_exclusive=require_member_exclusive,
        )
        return save_resolved_episodes_per_season_desc(
            s,
            show=show,
            season=season,
            episodes=resolved,
            start_index=start_index,
        )
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

    Remote episode details are resolved before the first write so no database
    writer lock is held while waiting on Daily Wire.

    Returns the next index to use for subsequent (newer) episodes together with the
    episodes that were saved.
    """
    try:
        resolved = resolve_dw_episodes(
            episodes=episodes,
            client=client,
            require_member_exclusive=require_member_exclusive,
        )
        return save_resolved_episodes_per_season_asc(
            s,
            show=show,
            season=season,
            episodes=resolved,
            start_index=start_index,
        )
    except Exception:
        s.rollback()
        raise