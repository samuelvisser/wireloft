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
from .no_show import is_no_show_today_slug
from .status import is_published_final, observe_episode_detail, resolve_episode_status
from .unusable_media import (
    NoUsableMediaReason,
    clear_episode_no_usable_media_tracking,
    mark_episode_no_usable_media,
)


logger = logging.getLogger(__name__)


@dataclass
class SavedEpisode:
    episode: Episode
    status: EpisodePublishStatus
    detail_resolved: bool


@dataclass(frozen=True)
class ResolvedEpisode:
    episode_identifier: str
    record: DwEpisodeRecord
    status: EpisodePublishStatus
    detail_resolved: bool
    unusable_media_reason: NoUsableMediaReason | None = None


def upsert_episode(
        s: Session, *, show: Show, season: Season, ep: DwEpisodeRecord, index_value: int, ep_id: str
) -> Episode:
    episode: Optional[Episode] = (
        s.query(Episode)
        .filter(Episode.show_id == show.id, Episode.slug == ep.slug)
        .one_or_none()
    )
    was_created = episode is None

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
                "metadata_is_final": metadata_is_final_for_new_episode(
                    ep.publish_status,
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
        episode.publish_status = ep.publish_status
        episode.metadata_is_final = metadata_is_final_for_new_episode(
            ep.publish_status,
            ep.published_date,
        )
    s.flush()

    if (
        was_created
        and episode.publish_status == EpisodePublishStatus.PUBLISHED_FINAL.value
        and not episode.metadata_is_final
    ):
        queue_event(s, METADATA_REFRESH_REQUESTED_EVENT, {"resource_id": episode.id, "id": episode.id})

    return episode


def resolve_dw_episodes(
        *,
        episodes: list[EpisodeWithIdentifier],
        client: MiddlewareClient,
        require_member_exclusive: bool,
        always_resolve_details: bool = False,
) -> list[ResolvedEpisode]:
    """Resolve remote snapshot + WireLoft transition policy before database writes."""
    resolved: list[ResolvedEpisode] = []
    for ep_id, ep in episodes:
        reason: NoUsableMediaReason | None = None

        if is_no_show_today_slug(ep.slug):
            status = EpisodePublishStatus.NO_USABLE_MEDIA
            record: DwEpisodeRecord = ep
            detail_resolved = True
            reason = NoUsableMediaReason.NO_SHOW_TODAY
        elif is_published_final(ep) and not always_resolve_details:
            status = EpisodePublishStatus.PUBLISHED_FINAL
            record = ep
            detail_resolved = False
        else:
            try:
                detail = client.get_episode_details(
                    ep.slug,
                    require_member_exclusive=require_member_exclusive,
                )
            except MiddlewareAPIError as exc:
                if exc.status_code != 404:
                    raise
                logger.info("Daily Wire returned 404 while resolving new episode %s", ep.slug)
                record = ep
                status = EpisodePublishStatus.NO_USABLE_MEDIA
                detail_resolved = True
                reason = NoUsableMediaReason.NOT_FOUND
            else:
                observed = observe_episode_detail(detail)
                snapshot = resolve_episode_status(detail, snapshot=observed)
                record = detail
                status = snapshot.status
                detail_resolved = True
                if status is EpisodePublishStatus.NO_USABLE_MEDIA:
                    if is_no_show_today_slug(detail.slug):
                        reason = NoUsableMediaReason.NO_SHOW_TODAY
                    elif observed.status is EpisodePublishStatus.DW_PROCESSING:
                        reason = NoUsableMediaReason.PROCESSING_TIMEOUT
                    else:
                        reason = NoUsableMediaReason.MEDIA_UNUSABLE

        resolved.append(ResolvedEpisode(
            episode_identifier=ep_id,
            record=record,
            status=status,
            detail_resolved=detail_resolved,
            unusable_media_reason=reason,
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

    if resolved.status is EpisodePublishStatus.NO_USABLE_MEDIA:
        if resolved.unusable_media_reason is None:
            raise ValueError("NO_USABLE_MEDIA episodes require an unusable-media reason")
        mark_episode_no_usable_media(
            s,
            episode,
            reason=resolved.unusable_media_reason,
        )
    else:
        clear_episode_no_usable_media_tracking(episode)
    s.flush()

    return SavedEpisode(
        episode=episode,
        status=EpisodePublishStatus(episode.publish_status),
        detail_resolved=resolved.detail_resolved,
    )


def _save_resolved(
        s: Session,
        *,
        show: Show,
        season: Season,
        episodes: list[ResolvedEpisode],
        start_index: int,
        step: int,
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
            current_index += step
        s.commit()
        return current_index, saved
    except Exception:
        s.rollback()
        raise


def save_resolved_episodes_per_season_desc(s: Session, *, show: Show, season: Season, episodes: list[ResolvedEpisode], start_index: int):
    return _save_resolved(s, show=show, season=season, episodes=episodes, start_index=start_index, step=-1)


def save_resolved_episodes_per_season_asc(s: Session, *, show: Show, season: Season, episodes: list[ResolvedEpisode], start_index: int):
    return _save_resolved(s, show=show, season=season, episodes=episodes, start_index=start_index, step=1)


def save_dw_episodes_per_season_desc(s: Session, *, show: Show, season: Season, episodes: list[EpisodeWithIdentifier], start_index: int, client: MiddlewareClient, require_member_exclusive: bool, always_resolve_details: bool = False):
    resolved = resolve_dw_episodes(
        episodes=episodes,
        client=client,
        require_member_exclusive=require_member_exclusive,
        always_resolve_details=always_resolve_details,
    )
    return save_resolved_episodes_per_season_desc(
        s, show=show, season=season, episodes=resolved, start_index=start_index,
    )


def save_dw_episodes_per_season_asc(s: Session, *, show: Show, season: Season, episodes: list[EpisodeWithIdentifier], start_index: int, client: MiddlewareClient, require_member_exclusive: bool, always_resolve_details: bool = False):
    resolved = resolve_dw_episodes(
        episodes=episodes,
        client=client,
        require_member_exclusive=require_member_exclusive,
        always_resolve_details=always_resolve_details,
    )
    return save_resolved_episodes_per_season_asc(
        s, show=show, season=season, episodes=resolved, start_index=start_index,
    )
