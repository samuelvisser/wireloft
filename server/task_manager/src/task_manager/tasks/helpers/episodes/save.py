from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Optional

from sqlalchemy.orm import Session

from backend.api.helpers import update_database_fields, create_database_fields
from backend.db.models import Show, Season
from backend.db.models.media_item import Episode
from backend.types.episode_types import EpisodePublishStatus
from backend.utils.helpers import generate_uuid
from backend.types.media_types import MediaType

from dailywire_api.dw_api.client import MiddlewareAPIError, MiddlewareClient
from dailywire_api.records import DwEpisodeRecord
from task_manager.events.transactional import queue_event
from .identifier import EpisodeWithIdentifier
from .metadata import METADATA_REFRESH_REQUESTED_EVENT, metadata_is_final_for_new_episode
from .no_show import is_no_show_today_title
from .processing import (
    DwProcessingReason,
    clear_episode_dw_processing_tracking,
    mark_episode_dw_processing,
)
from .status import is_published_final, get_publish_status_from_dw_detail


logger = logging.getLogger(__name__)


@dataclass
class SavedEpisode:
    """The outcome of persisting one remote episode."""
    episode: Episode
    status: EpisodePublishStatus
    detail_resolved: bool


@dataclass(frozen=True)
class ResolvedEpisode:
    """An episode whose remote detail work is complete and is ready to persist."""
    episode_identifier: str
    record: DwEpisodeRecord
    status: EpisodePublishStatus
    detail_resolved: bool
    processing_reason: DwProcessingReason | None = None


def upsert_episode(
        s, *, show: Show, season: Season, ep: DwEpisodeRecord, index_value: int, ep_id: str
) -> Episode:
    """Create or update a single Episode row for the given EpisodeRecord."""
    episode: Optional[Episode] = (
        s.query(Episode)
        .filter(Episode.show_id == show.id, Episode.slug == ep.slug)
        .one_or_none()
    )
    was_created = episode is None
    is_no_show_today = is_no_show_today_title(ep.title)
    effective_publish_status = (
        EpisodePublishStatus.DW_PROCESSING.value
        if is_no_show_today
        else ep.publish_status
    )

    if was_created:
        episode = create_database_fields(Episode, data={
            **ep.model_dump(mode="python", by_alias=False),
            **{
                "uuid": generate_uuid(),
                "type": MediaType.EPISODE.value,
                "show_id": show.id,
                "season_id": season.id,
                "index": index_value,
                "episode_identifier": ep_id,
                "publish_status": effective_publish_status,
                "is_no_show_today": is_no_show_today,
                "metadata_is_final": metadata_is_final_for_new_episode(
                    effective_publish_status,
                    ep.published_date,
                ),
            }
        })
        s.add(episode)
    else:
        update_database_fields(episode, ep, ignore_extra_fields=True)
        episode.season_id = season.id
        episode.index = index_value
        episode.episode_identifier = ep_id
        episode.publish_status = effective_publish_status
        episode.is_no_show_today = is_no_show_today

    s.flush()

    if is_no_show_today:
        mark_episode_dw_processing(
            episode,
            reason=DwProcessingReason.NO_SHOW_TODAY,
        )
    elif effective_publish_status != EpisodePublishStatus.DW_PROCESSING.value:
        clear_episode_dw_processing_tracking(episode)

    s.flush()

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
        always_resolve_details: bool = False,
) -> list[ResolvedEpisode]:
    """Resolve remote detail state before entering the database write phase.

    Initial back-catalog indexing may safely use the published-final shortcut to
    avoid thousands of detail calls. Incremental discovery sets
    ``always_resolve_details`` so every newly seen item gets one authoritative
    detail lookup: the final-timeout fallback still wins on a successful response,
    while a current 404 can override it with DW_PROCESSING.
    """
    resolved: list[ResolvedEpisode] = []
    for ep_id, ep in episodes:
        processing_reason: DwProcessingReason | None = None

        if is_no_show_today_title(ep.title):
            status = EpisodePublishStatus.DW_PROCESSING
            record: DwEpisodeRecord = ep
            detail_resolved = True
            processing_reason = DwProcessingReason.NO_SHOW_TODAY
        elif is_published_final(ep) and not always_resolve_details:
            status = EpisodePublishStatus.PUBLISHED_FINAL
            record = ep
            detail_resolved = False
        else:
            try:
                record = client.get_episode_details(
                    ep.slug,
                    require_member_exclusive=require_member_exclusive,
                )
            except MiddlewareAPIError as exc:
                if exc.status_code != 404:
                    raise
                logger.info(
                    "Daily Wire returned 404 while resolving new episode %s; "
                    "persisting it as dw_processing",
                    ep.slug,
                )
                record = ep
                status = EpisodePublishStatus.DW_PROCESSING
                detail_resolved = True
                processing_reason = DwProcessingReason.NOT_FOUND
            else:
                status = get_publish_status_from_dw_detail(record)
                detail_resolved = True
                if status is EpisodePublishStatus.DW_PROCESSING:
                    processing_reason = (
                        DwProcessingReason.NO_SHOW_TODAY
                        if is_no_show_today_title(record.title)
                        else DwProcessingReason.DAILY_WIRE
                    )

        resolved.append(ResolvedEpisode(
            episode_identifier=ep_id,
            record=record,
            status=status,
            detail_resolved=detail_resolved,
            processing_reason=processing_reason,
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

    if resolved.status is EpisodePublishStatus.DW_PROCESSING:
        mark_episode_dw_processing(
            episode,
            reason=resolved.processing_reason or DwProcessingReason.DAILY_WIRE,
        )
    else:
        clear_episode_dw_processing_tracking(episode)
    s.flush()

    return SavedEpisode(
        episode=episode,
        status=EpisodePublishStatus(episode.publish_status),
        detail_resolved=resolved.detail_resolved,
    )


def save_resolved_episodes_per_season_desc(
        s: Session, *,
        show: Show,
        season: Season,
        episodes: list[ResolvedEpisode],
        start_index: int,
) -> tuple[int, list[SavedEpisode]]:
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
                                     require_member_exclusive: bool,
                                     always_resolve_details: bool = False) -> tuple[int, list[SavedEpisode]]:
    try:
        resolved = resolve_dw_episodes(
            episodes=episodes,
            client=client,
            require_member_exclusive=require_member_exclusive,
            always_resolve_details=always_resolve_details,
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
                                    require_member_exclusive: bool,
                                    always_resolve_details: bool = False) -> tuple[int, list[SavedEpisode]]:
    try:
        resolved = resolve_dw_episodes(
            episodes=episodes,
            client=client,
            require_member_exclusive=require_member_exclusive,
            always_resolve_details=always_resolve_details,
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
