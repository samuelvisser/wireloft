from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models import Episode
from backend.types.episode_types import EpisodePublishStatus
from dailywire_api.dw_api.client import MiddlewareClient
from dailywire_api.types.user_info import DwMembershipLevel
from task_manager.scheduler.executor import trigger_now
from ...helpers.episodes.metadata import (
    metadata_refresh_offsets_seconds,
    metadata_watch_expired,
    update_episode_from_dailywire,
)
from .scheduling import remove_episode_metadata_jobs, schedule_remaining_metadata_checks


logger = logging.getLogger(__name__)
_TASK_KEY = "refresh_episode_metadata_worker"


async def run_refresh_episode_metadata_worker(
        s: Session,
        *,
        episode_id: int | None,
        refresh: bool = False,
        scheduled_offset_seconds: int | None = None,
) -> None:
    """Refresh or schedule post-publication metadata reconciliation for episodes."""
    if episode_id is None:
        _queue_startup_recovery(s)
        return

    episode = s.get(Episode, episode_id)
    if episode is None:
        # A one-shot job can outlive an episode that was deleted in the meantime.
        logger.info("Skipping metadata refresh for deleted episode %s", episode_id)
        return

    if episode.metadata_is_final:
        remove_episode_metadata_jobs(episode.id)
        return

    if episode.publish_status != EpisodePublishStatus.PUBLISHED_FINAL.value:
        # The normal monitor already keeps live/non-final metadata fresh. A manual
        # refresh still performs one explicit detail request, but finality remains
        # false so the ordinary post-publication flow can finish it later.
        if refresh:
            _refresh_episode_from_dailywire(s, episode)
            episode.metadata_is_final = False
            s.commit()
        return

    configured_offsets = metadata_refresh_offsets_seconds()
    if (
        refresh
        and scheduled_offset_seconds is not None
        and scheduled_offset_seconds not in configured_offsets
    ):
        # The setting may have changed after this one-shot job was created. Do not
        # perform an obsolete check; rebuild the remaining schedule instead.
        refresh = False

    if refresh:
        _refresh_episode_from_dailywire(s, episode)

    now = datetime.now(timezone.utc)
    if refresh and metadata_watch_expired(episode.published_date, now=now):
        episode.metadata_is_final = True
        s.commit()
        remove_episode_metadata_jobs(episode.id)
        logger.info("Episode %s metadata is final", episode.id)
        return

    pending_jobs = schedule_remaining_metadata_checks(
        episode_id=episode.id,
        published_date=episode.published_date,
        now=now,
    )

    if refresh:
        # Persist every successful metadata reconciliation, even when more checks
        # remain. A failed fetch raises before this point and leaves the flag false.
        s.commit()

    if not pending_jobs and metadata_watch_expired(episode.published_date, now=now):
        # This setup path can occur after a settings change. Ensure finality is only
        # recorded after a real detail refresh, just like startup recovery.
        trigger_now(
            def_key=_TASK_KEY,
            resource_type="episode",
            resource_id=episode.id,
            refresh=True,
        )


def _queue_startup_recovery(s: Session) -> None:
    """Immediately refresh every unfinished finalized episode after a restart."""
    episode_ids = list(
        s.scalars(
            select(Episode.id).where(
                Episode.metadata_is_final.is_(False),
                Episode.publish_status == EpisodePublishStatus.PUBLISHED_FINAL.value,
            )
        )
    )
    for episode_id in episode_ids:
        # Run each episode as its own task so normal worker retry policy applies to
        # individual Daily Wire failures without blocking recovery of the others.
        trigger_now(
            def_key=_TASK_KEY,
            resource_type="episode",
            resource_id=episode_id,
            refresh=True,
        )

    if episode_ids:
        logger.info(
            "Queued immediate metadata recovery for %s episode(s)",
            len(episode_ids),
        )


def _refresh_episode_from_dailywire(s: Session, episode: Episode) -> None:
    show = episode.show
    client = MiddlewareClient()
    dw_episode = client.get_episode_details(
        episode.slug,
        require_member_exclusive=(
            show.membership_level != DwMembershipLevel.FREE.value
        ),
    )
    update_episode_from_dailywire(episode, dw_episode)
    s.flush()
    logger.info("Refreshed Daily Wire metadata for episode %s", episode.id)
