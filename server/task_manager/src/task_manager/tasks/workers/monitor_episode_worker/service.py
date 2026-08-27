from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy.orm import Session

from backend.db.models import Episode, Show
from backend.types.episode_types import EpisodePublishStatus
from dailywire_api.dw_api.client import MiddlewareClient
from dailywire_api.records import DwEpisodeDetailRecord
from dailywire_api.types.user_info import DwMembershipLevel
from task_manager.events.transactional import queue_event

from ._helpers import save_status_metadata
from .scheduling import MONITOR_COMPLETED_EVENT
from ...helpers.episodes.events import episode_event_payload, queue_episode_status_events
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
    """Refresh one already-indexed non-final episode and persist its current state.

    ``fetch_new_episodes`` is responsible for creating the episode row (with its
    initial non-final status). This worker only drives an existing episode forward
    until it reaches ``PUBLISHED_FINAL``. ``season_id``/``episode_identifier``/
    ``episode_index`` are accepted for scheduler compatibility and used only as
    lookup hints.
    """
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

    client = MiddlewareClient()
    dw_episode = client.get_episode_details(
        episode_slug or db_episode.slug,
        require_member_exclusive=(
            show.membership_level != DwMembershipLevel.FREE.value
        ),
    )
    new_status = get_publish_status_from_dw_detail(dw_episode)

    old_status = db_episode.publish_status

    _update_episode_from_dailywire(db_episode, dw_episode)
    db_episode.publish_status = new_status.value
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

    if new_status is EpisodePublishStatus.PUBLISHED_FINAL:
        queue_event(
            s,
            MONITOR_COMPLETED_EVENT,
            episode_event_payload(episode=db_episode, show=show, old_status=old_status),
        )

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


def _update_episode_from_dailywire(
        episode: Episode,
        dw_episode: DwEpisodeDetailRecord,
) -> None:
    """Update remote fields without changing Wireloft identity fields."""
    protected_fields = {
        "id",
        "show_id",
        "season_id",
        "index",
        "episode_identifier",
        "publish_status",
    }
    model_fields = set(Episode.__mapper__.attrs.keys())
    for field, value in dw_episode.model_dump(
            mode="python",
            by_alias=False,
    ).items():
        if field in model_fields and field not in protected_fields:
            setattr(episode, field, value)
