from __future__ import annotations

from sqlalchemy.orm import Session

from backend.db.models import Episode, Show
from backend.types.episode_types import EpisodePublishStatus
from task_manager.events.transactional import queue_event


EPISODE_IDENTIFIER_CHANGED_EVENT = "episode.identifier_changed"
_EPISODE_WAS_PUBLISHED_META_KEY = "ep_status.was_published"
_PUBLISHED_STATUSES = frozenset({
    EpisodePublishStatus.PUBLISHED_WITH_COUNTDOWN.value,
    EpisodePublishStatus.PUBLISHED_FINAL.value,
})


def episode_event_payload(
        *,
        episode: Episode,
        show: Show,
        old_status: str | None = None,
) -> dict:
    """Build the standard payload emitted for episode status-lifecycle events."""
    return {
        "resource_id": episode.id,
        "id": episode.id,
        "slug": episode.slug,
        "show_id": show.id,
        "show_slug": show.slug,
        "season_id": episode.season_id,
        "episode_identifier": episode.episode_identifier,
        "episode_index": episode.index,
        "old_status": old_status,
        "status": episode.publish_status,
    }


def episode_was_published(
        episode: Episode,
        *,
        previous_publish_status: str | None = None,
) -> bool:
    """Return whether this row had already reached a playable publication phase."""
    if episode.get_meta(_EPISODE_WAS_PUBLISHED_META_KEY) == "1":
        return True

    # When the caller captured the status before applying fresh Daily Wire data,
    # that old status defines whether the identifier changed *after* publication.
    # In particular, LIVE -> PUBLISHED_FINAL plus an identifier correction in the
    # same poll is still the initial publication and needs no artifact repair yet.
    status = (
        previous_publish_status
        if previous_publish_status is not None
        else episode.publish_status
    )
    return status in _PUBLISHED_STATUSES


def queue_episode_identifier_changed_event(
        s: Session,
        *,
        episode: Episode,
        old_episode_identifier: str,
        previous_publish_status: str | None = None,
) -> bool:
    """Emit the system-wide identifier-change event only for already-published media.

    Identifier corrections before initial publication are harmless to downstream
    artifacts because no Download Profile should have created playable media yet.
    Once an episode has reached a published phase, however, changing its identifier
    can invalidate persisted output paths and other consumers of that identifier.
    """
    if not episode_was_published(
        episode,
        previous_publish_status=previous_publish_status,
    ):
        return False

    payload = episode_event_payload(
        episode=episode,
        show=episode.show,
        old_status=previous_publish_status,
    )
    payload.update({
        "old_episode_identifier": old_episode_identifier,
        "new_episode_identifier": episode.episode_identifier,
    })
    queue_event(s, EPISODE_IDENTIFIER_CHANGED_EVENT, payload)
    return True


def _remember_episode_was_published(
        episode: Episode,
        *statuses: str | None,
) -> None:
    if episode.get_meta(_EPISODE_WAS_PUBLISHED_META_KEY) == "1":
        return
    if any(status in _PUBLISHED_STATUSES for status in statuses):
        episode.set_meta(_EPISODE_WAS_PUBLISHED_META_KEY, "1")


def queue_episode_status_events(
        s: Session,
        *,
        episode: Episode,
        show: Show,
        old_status: str | None,
        new_status: EpisodePublishStatus,
        was_created: bool,
) -> None:
    """Queue the episode status-lifecycle events for a created/updated episode.

    Mirrors the single source of truth for "an episode appeared or changed phase":
    ``episode.added`` on creation, and ``episode.status_updated`` plus the
    phase-specific ``published_with_countdown`` / ``published_final`` events whenever
    the resolved status differs from the previous one. Job-lifecycle events (such as
    the monitor-completed event) are intentionally left to their owning worker.

    Publication history is also remembered independently of the current status so
    a later Daily Wire 404/DW_PROCESSING regression cannot make WireLoft forget that
    identifier changes may already invalidate downloaded files.
    """
    _remember_episode_was_published(
        episode,
        old_status,
        new_status.value,
    )

    event_data = episode_event_payload(
        episode=episode,
        show=show,
        old_status=old_status,
    )

    if was_created:
        queue_event(s, "episode.added", event_data)

    if old_status != new_status.value:
        queue_event(s, "episode.status_updated", event_data)
        if new_status is EpisodePublishStatus.PUBLISHED_WITH_COUNTDOWN:
            queue_event(s, "episode.published_with_countdown", event_data)
        elif new_status is EpisodePublishStatus.PUBLISHED_FINAL:
            queue_event(s, "episode.published_final", event_data)
