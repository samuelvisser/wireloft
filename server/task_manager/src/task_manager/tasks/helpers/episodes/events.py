from __future__ import annotations

from sqlalchemy.orm import Session

from backend.db.models import Episode, Show
from backend.types.episode_types import EpisodePublishStatus
from task_manager.events.transactional import queue_event


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
    """
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
