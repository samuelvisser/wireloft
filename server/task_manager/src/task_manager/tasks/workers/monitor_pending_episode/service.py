from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from backend.db.models import Episode, Show
from backend.types.dailywire_user_info import WlDwMembershipLevel
from backend.types.episode_types import EpisodePublishStatus
from dailywire_api.dw_api.client import ByShowSeason, MiddlewareAPIError, MiddlewareClient
from task_manager.events.transactional import queue_event

from ._helpers import save_status_metadata
from .scheduling import queue_monitor_completion_if_settled
from ...helpers.episodes.events import queue_episode_status_events
from ...helpers.episodes.identifier_reconciliation import reconcile_episode_identifier
from ...helpers.episodes.mapper import fetch_all_episodes_paginated
from ...helpers.episodes.metadata import (
    METADATA_REFRESH_REQUESTED_EVENT,
    metadata_watch_expired,
    update_episode_from_dailywire,
)
from ...helpers.episodes.no_show import is_no_show_today_slug
from ...helpers.episodes.same_episode import (
    PENDING_EPISODE_STATUSES,
    reconcile_single_pending_episode_slug,
)
from ...helpers.episodes.status import observe_episode_detail, resolve_episode_status
from ...helpers.episodes.unusable_media import (
    NoUsableMediaReason,
    clear_episode_no_usable_media_tracking,
    mark_episode_no_usable_media,
)
from ...helpers.shows.get import get_show_from_params


logger = logging.getLogger(__name__)


def _membership_plan(show: Show) -> tuple[str, bool]:
    membership_plan = show.membership_level
    if membership_plan == WlDwMembershipLevel.WL_ANY.value:
        return WlDwMembershipLevel.FREE.value, False
    return membership_plan, membership_plan != WlDwMembershipLevel.FREE.value


def _find_episode(
    s: Session,
    *,
    show: Show,
    episode_id: int | None,
    episode_slug: str | None,
    episode_identifier: str | None,
) -> Episode | None:
    if episode_id is not None:
        episode = s.get(Episode, episode_id)
        if episode is not None:
            return episode
    if episode_slug is not None:
        episode = (
            s.query(Episode)
            .filter(Episode.show_id == show.id, Episode.slug == episode_slug)
            .one_or_none()
        )
        if episode is not None:
            return episode
    if episode_identifier is None:
        return None
    return (
        s.query(Episode)
        .filter(
            Episode.show_id == show.id,
            Episode.episode_identifier == episode_identifier,
        )
        .one_or_none()
    )


def _reload_episode_and_show(
    s: Session,
    *,
    episode_id: int,
    show_id: int,
) -> tuple[Episode, Show]:
    show = s.get(Show, show_id)
    episode = s.get(Episode, episode_id)
    if show is None or episode is None:
        raise ValueError("Pending episode or show was removed while it was being refreshed")
    return episode, show


def _try_reconcile_slug_after_404(
    s: Session,
    *,
    client: MiddlewareClient,
    show: Show,
    episode: Episode,
) -> str | None:
    """Try the same conservative pending-slug reconciliation used by discovery.

    Remote requests deliberately run outside a database transaction. This worker
    can fan out across many pending episodes, so retaining one checked-out
    connection per request can otherwise exhaust the pool during an outage.
    """
    membership_plan, _ = _membership_plan(show)
    show_id = show.id
    episode_id = episode.id
    show_slug = show.slug
    season_slug = episode.season.slug
    s.rollback()

    show_page = client.get_show_page(show_slug, membership_plan=membership_plan)
    remote_season = next(
        (candidate for candidate in show_page.seasons if candidate.slug == season_slug),
        None,
    )
    if remote_season is None:
        return None

    records = fetch_all_episodes_paginated(
        client,
        show_slug,
        ByShowSeason(
            season_dw_id=remote_season.dw_id,
            membership_plan=membership_plan,
            page_size=50,
            order_by="CreatedAt_ASC",
        ),
    )

    episode, show = _reload_episode_and_show(
        s,
        episode_id=episode_id,
        show_id=show_id,
    )
    reconciled = reconcile_single_pending_episode_slug(
        s,
        show=show,
        season=episode.season,
        remote_records=records,
    )
    if reconciled is None or reconciled.id != episode.id:
        s.rollback()
        return None

    reconciled_slug = reconciled.slug
    s.commit()
    return reconciled_slug


def _no_usable_reason(detail, *, observed_status: EpisodePublishStatus) -> NoUsableMediaReason:
    if is_no_show_today_slug(detail.slug):
        return NoUsableMediaReason.NO_SHOW_TODAY
    if observed_status is EpisodePublishStatus.DW_PROCESSING:
        return NoUsableMediaReason.PROCESSING_TIMEOUT
    return NoUsableMediaReason.MEDIA_UNUSABLE


def _quarantine_404(
    s: Session,
    *,
    episode: Episode,
    show: Show,
    old_status: str,
) -> EpisodePublishStatus:
    new_status = EpisodePublishStatus.NO_USABLE_MEDIA
    mark_episode_no_usable_media(
        s,
        episode,
        reason=NoUsableMediaReason.NOT_FOUND,
    )
    queue_episode_status_events(
        s,
        episode=episode,
        show=show,
        old_status=old_status,
        new_status=new_status,
        was_created=False,
    )
    queue_monitor_completion_if_settled(
        s,
        episode=episode,
        show=show,
        old_status=old_status,
    )
    s.commit()
    logger.info(
        "Daily Wire returned 404 for pending episode %s; status %s -> %s",
        episode.id,
        old_status,
        new_status.value,
    )
    return new_status


async def run_monitor_pending_episode(
    s: Session,
    *,
    episode_id: Optional[int] = None,
    episode_slug: Optional[str] = None,
    show_id: Optional[int] = None,
    show_slug: Optional[str] = None,
    season_id: Optional[int] = None,
    episode_identifier: Optional[str] = None,
    episode_index: Optional[int] = None,
) -> EpisodePublishStatus:
    """Refresh one pending episode until ownership transfers to another stage."""
    del season_id, episode_index
    print(f"Starting monitor_pending_episode for {episode_slug or episode_id}")

    show = get_show_from_params(
        s,
        episode_id=episode_id,
        episode_slug=episode_slug,
        show_id=show_id,
        show_slug=show_slug,
    )
    if show is None:
        raise ValueError("Show not found; provide a valid show_slug or show_id")

    episode = _find_episode(
        s,
        show=show,
        episode_id=episode_id,
        episode_slug=episode_slug,
        episode_identifier=episode_identifier,
    )
    if episode is None:
        raise ValueError(
            "Pending episode not found in database; "
            "fetch_new_episodes must index it first"
        )

    old_status = episode.publish_status
    if old_status not in PENDING_EPISODE_STATUSES:
        queue_monitor_completion_if_settled(
            s,
            episode=episode,
            show=show,
            old_status=old_status,
        )
        s.commit()
        return EpisodePublishStatus(old_status)

    episode_db_id = episode.id
    show_db_id = show.id
    request_slug = episode.slug
    _, require_member_exclusive = _membership_plan(show)
    client = MiddlewareClient()

    # A SELECT starts an ORM transaction. Release it before DNS/HTTP/HLS work so
    # concurrent episode monitors cannot consume the whole DB pool while offline.
    s.rollback()
    try:
        detail = client.get_episode_details(
            request_slug,
            require_member_exclusive=require_member_exclusive,
        )
    except MiddlewareAPIError as exc:
        if exc.status_code != 404:
            raise

        episode, show = _reload_episode_and_show(
            s,
            episode_id=episode_db_id,
            show_id=show_db_id,
        )
        reconciled_slug = _try_reconcile_slug_after_404(
            s,
            client=client,
            show=show,
            episode=episode,
        )
        if reconciled_slug is None:
            episode, show = _reload_episode_and_show(
                s,
                episode_id=episode_db_id,
                show_id=show_db_id,
            )
            return _quarantine_404(
                s,
                episode=episode,
                show=show,
                old_status=episode.publish_status,
            )

        try:
            detail = client.get_episode_details(
                reconciled_slug,
                require_member_exclusive=require_member_exclusive,
            )
        except MiddlewareAPIError as reconciled_exc:
            if reconciled_exc.status_code != 404:
                raise
            episode, show = _reload_episode_and_show(
                s,
                episode_id=episode_db_id,
                show_id=show_db_id,
            )
            return _quarantine_404(
                s,
                episode=episode,
                show=show,
                old_status=episode.publish_status,
            )

    # Media inspection can itself fetch HLS manifests. Keep that I/O outside the
    # ORM transaction as well, then reload current rows before applying the result.
    observed = observe_episode_detail(detail)
    resolved = resolve_episode_status(detail, snapshot=observed)
    new_status = resolved.status

    episode, show = _reload_episode_and_show(
        s,
        episode_id=episode_db_id,
        show_id=show_db_id,
    )
    old_status = episode.publish_status
    if old_status not in PENDING_EPISODE_STATUSES:
        queue_monitor_completion_if_settled(
            s,
            episode=episode,
            show=show,
            old_status=old_status,
        )
        s.commit()
        return EpisodePublishStatus(old_status)

    update_episode_from_dailywire(episode, detail)
    if new_status is EpisodePublishStatus.NO_USABLE_MEDIA:
        mark_episode_no_usable_media(
            s,
            episode,
            reason=_no_usable_reason(detail, observed_status=observed.status),
        )
    else:
        episode.publish_status = new_status.value
        clear_episode_no_usable_media_tracking(episode)
        episode.metadata_is_final = (
            metadata_watch_expired(episode.published_date)
            if new_status is EpisodePublishStatus.PUBLISHED_FINAL
            else False
        )
        reconcile_episode_identifier(
            s,
            episode,
            detail,
            previous_publish_status=old_status,
        )

    if new_status.value in PENDING_EPISODE_STATUSES:
        save_status_metadata(
            s,
            episode=episode,
            dw_episode=detail,
            status=new_status,
        )
    elif (
        new_status is EpisodePublishStatus.PUBLISHED_FINAL
        and not episode.metadata_is_final
    ):
        queue_event(
            s,
            METADATA_REFRESH_REQUESTED_EVENT,
            {"resource_id": episode.id, "id": episode.id},
        )

    queue_episode_status_events(
        s,
        episode=episode,
        show=show,
        old_status=old_status,
        new_status=new_status,
        was_created=False,
    )
    queue_monitor_completion_if_settled(
        s,
        episode=episode,
        show=show,
        old_status=old_status,
    )
    s.commit()

    logger.info("Episode %s status: %s -> %s", episode.id, old_status, new_status.value)
    print(f"monitor_pending_episode completed for {episode.slug}: {new_status.value}")
    return new_status
