from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from backend.db.models import Episode, Show
from backend.types.episode_types import EpisodePublishStatus
from dailywire_api.dw_api.client import MiddlewareAPIError, MiddlewareClient
from dailywire_api.types.user_info import DwMembershipLevel
from task_manager.events.transactional import queue_event

from ._helpers import save_status_metadata
from .scheduling import MONITOR_COMPLETED_EVENT, MONITOR_REQUESTED_EVENT
from ...helpers.episodes.events import episode_event_payload, queue_episode_status_events
from ...helpers.episodes.identifier_reconciliation import reconcile_episode_identifier
from ...helpers.episodes.metadata import metadata_watch_expired, update_episode_from_dailywire
from ...helpers.episodes.unusable_media import (
    NoUsableMediaReason,
    clear_episode_no_usable_media_tracking,
    mark_episode_no_usable_media,
)
from ...helpers.episodes.status import get_publish_status_from_dw_detail
from ...helpers.shows.get import get_show_from_params


logger = logging.getLogger(__name__)


async def run_monitor_episode_worker(
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
    """Refresh one already-indexed non-final episode until its lifecycle settles."""
    print(f"Starting monitor_episode_worker for {episode_slug or episode_id}")

    show = get_show_from_params(
        s,
        episode_id=episode_id,
        episode_slug=episode_slug,
        show_id=show_id,
        show_slug=show_slug,
    )
    if show is None:
        raise ValueError("Show not found; provide a valid show_slug or show_id")

    db_episode = _find_episode(
        s,
        show=show,
        episode_id=episode_id,
        episode_slug=episode_slug,
        episode_identifier=episode_identifier,
    )
    if db_episode is None:
        raise ValueError(
            "Monitored episode not found in database; "
            "fetch_new_episodes must index it before monitoring"
        )

    # The recurring APScheduler job is keyed by the identifier it was scheduled
    # with. Keep that identity separately from the mutable database identifier so
    # a Daily Wire correction can safely re-key or remove the current monitor job.
    monitor_job_identifier = episode_identifier or db_episode.episode_identifier

    client = MiddlewareClient()
    try:
        dw_episode = client.get_episode_details(
            db_episode.slug,
            require_member_exclusive=(
                show.membership_level != DwMembershipLevel.FREE.value
            ),
        )
    except MiddlewareAPIError as exc:
        if exc.status_code != 404:
            raise

        # A list entry whose detail endpoint currently 404s has no usable media.
        # Keep it under the monitor lifecycle, but use the dedicated status rather
        # than conflating this with genuine Daily Wire processing. Repeated 404s
        # preserve the first-observed timestamp for the cleanup worker.
        old_status = db_episode.publish_status
        new_status = EpisodePublishStatus.NO_USABLE_MEDIA
        mark_episode_no_usable_media(
            db_episode,
            reason=NoUsableMediaReason.NOT_FOUND,
        )
        s.flush()
        queue_episode_status_events(
            s,
            episode=db_episode,
            show=show,
            old_status=old_status,
            new_status=new_status,
            was_created=False,
        )
        s.commit()

        logger.info(
            "Daily Wire returned 404 for monitored episode %s; status %s -> %s",
            db_episode.slug,
            old_status,
            new_status.value,
        )
        print(
            f"monitor_episode_worker completed for {db_episode.slug}: "
            f"{new_status.value} (Daily Wire returned 404)"
        )
        return new_status

    new_status = get_publish_status_from_dw_detail(dw_episode)
    old_status = db_episode.publish_status

    update_episode_from_dailywire(db_episode, dw_episode)
    if new_status is EpisodePublishStatus.NO_USABLE_MEDIA:
        mark_episode_no_usable_media(
            db_episode,
            reason=NoUsableMediaReason.NO_SHOW_TODAY,
        )
    else:
        db_episode.publish_status = new_status.value
        clear_episode_no_usable_media_tracking(db_episode)
        if new_status is EpisodePublishStatus.PUBLISHED_FINAL:
            # This poll itself is a fresh metadata check. If the entire configured
            # settling window has already elapsed, no follow-up work is required.
            db_episode.metadata_is_final = metadata_watch_expired(db_episode.published_date)
        else:
            db_episode.metadata_is_final = False

    # Use the exact same authoritative reconciliation path as metadata refresh.
    # Daily Wire sometimes changes episodeNumber while an episode is still live or
    # processing, so waiting for the post-publication metadata worker can leave the
    # row misclassified for the entire pre-publication lifecycle. The old status is
    # passed explicitly so a correction made on the first publication transition
    # is not mistaken for a post-publication identifier change.
    identifier_changed = False
    if not db_episode.is_no_show_today:
        identifier_changed = reconcile_episode_identifier(
            s,
            db_episode,
            dw_episode,
            previous_publish_status=old_status,
        )
    s.flush()

    save_status_metadata(
        s,
        episode=db_episode,
        dw_episode=dw_episode,
        status=new_status,
    )

    queue_episode_status_events(
        s,
        episode=db_episode,
        show=show,
        old_status=old_status,
        new_status=new_status,
        was_created=False,
    )

    monitor_should_continue = (
        new_status is not EpisodePublishStatus.PUBLISHED_FINAL
        and not db_episode.is_no_show_today
    )

    if identifier_changed:
        # Remove the recurring job under the identifier it was originally keyed
        # with. If monitoring still needs to continue, immediately recreate the
        # job using the corrected identifier. Both events are transactional, so a
        # failed database commit cannot desynchronize scheduler state from the row.
        completion_payload = episode_event_payload(
            episode=db_episode,
            show=show,
            old_status=old_status,
        )
        completion_payload["episode_identifier"] = monitor_job_identifier
        queue_event(s, MONITOR_COMPLETED_EVENT, completion_payload)

        if monitor_should_continue:
            queue_event(
                s,
                MONITOR_REQUESTED_EVENT,
                episode_event_payload(
                    episode=db_episode,
                    show=show,
                    old_status=old_status,
                ),
            )
    elif not monitor_should_continue:
        # Even if the identifier was corrected by an earlier monitor pass, the
        # currently executing recurring job may still carry its old identifier in
        # its kwargs until the queued re-key event is processed. Always remove the
        # job by that scheduled identity rather than by the mutable database value.
        completion_payload = episode_event_payload(
            episode=db_episode,
            show=show,
            old_status=old_status,
        )
        completion_payload["episode_identifier"] = monitor_job_identifier
        queue_event(s, MONITOR_COMPLETED_EVENT, completion_payload)

    s.commit()

    logger.info(
        "Episode %s status: %s -> %s",
        db_episode.slug,
        old_status,
        new_status.value,
    )
    print(
        f"monitor_episode_worker completed for {db_episode.slug}: "
        f"{new_status.value}"
    )
    return new_status


def _find_episode(
        s: Session,
        *,
        show: Show,
        episode_id: int | None,
        episode_slug: str | None,
        episode_identifier: str | None,
) -> Episode | None:
    if episode_id is not None:
        episode = (
            s.query(Episode)
            .filter(Episode.id == episode_id)
            .one_or_none()
        )
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
