from typing import Optional, assert_never

from backend.db.models import Show, Episode

from asyncio.log import logger

from sqlalchemy.orm import Session

from backend.types.episode_types import EpisodePublishStatus
from dailywire_api.records import DwEpisodeRecord
from wireloft_controller.tasks.helpers.episodes.status import get_publish_status_from_dw


def get_show_from_params(s: Session, *,
                         episode_id: Optional[int] = None,
                         episode_slug: Optional[str] = None,
                         show_id: Optional[int] = None,
                         show_slug: Optional[str] = None) -> Optional[Show]:
    if show_id is not None:
        return s.get(Show, show_id)
    if show_slug is not None:
        return s.query(Show).filter(Show.slug == show_slug).first()
    if episode_id is not None:
        return s.get(Episode, episode_id).show
    if episode_slug is not None:
        return s.query(Episode).filter(Episode.slug == episode_slug).first().show
    return None


def get_first_ep_with_status(eps: list[DwEpisodeRecord], status: EpisodePublishStatus) -> Optional[DwEpisodeRecord]:
    return next((ep for ep in eps if get_publish_status_from_dw(ep, None) == status), None)


def get_progress_updater_ep(latest_eps: list[DwEpisodeRecord]) -> DwEpisodeRecord:
    if len(latest_eps) == 0:
        raise ValueError("No episodes found")

    # If the latest is final, we can finish our tracking and use it
    if get_publish_status_from_dw(latest_eps[0], None) == EpisodePublishStatus.PUBLISHED_FINAL:
        return latest_eps[0]

    # At least the latest is not final, filter list, stopping with the first final
    index = next((i for i, rec in enumerate(latest_eps) if get_publish_status_from_dw(rec, None) == EpisodePublishStatus.PUBLISHED_FINAL), None)
    if index is not None:
        latest_eps = latest_eps[: index]

    # Return the episode that is furthest along in its publication process
    countdown_ep = get_first_ep_with_status(latest_eps, EpisodePublishStatus.PUBLISHED_WITH_COUNTDOWN)
    if countdown_ep:
        return countdown_ep

    processing_ep = get_first_ep_with_status(latest_eps, EpisodePublishStatus.DW_PROCESSING)
    if processing_ep:
        return processing_ep

    live_ep = get_first_ep_with_status(latest_eps, EpisodePublishStatus.LIVE)
    if live_ep:
        return live_ep

    delayed_ep = get_first_ep_with_status(latest_eps, EpisodePublishStatus.DELAYED)
    if delayed_ep:
        return delayed_ep

    scheduled_ep = get_first_ep_with_status(latest_eps, EpisodePublishStatus.SCHEDULED)
    if scheduled_ep:
        return scheduled_ep

    # If none of the above, return the latest
    logger.warning(f"No clear match found for most relevant progress updater episode")
    return latest_eps[-1]


def save_status_metadata(s: Session, *,
                         episode: Episode,
                         status: EpisodePublishStatus) -> None:
    match status:
        case status.SCHEDULED | status.LIVE:
            live_dw_id = episode.meta_items.get("ep_status.live.dw_id", None)
            if live_dw_id is None:
                episode.set_meta(key="ep_status.live.dw_id", value=episode.dw_id)
                episode.set_meta(key="ep_status.live.sharing_url", value=episode.sharing_url)
        case status.DELAYED:
            delayed_slug = episode.meta_items.get("ep_status.delayed.slug", None)
            if delayed_slug is None:
                episode.set_meta(key="ep_status.delayed.slug", value=episode.slug)
        case status.DW_PROCESSING:
            processing_dw_id = episode.meta_items.get("ep_status.dw_processing.dw_id", None)
            if processing_dw_id is None:
                episode.set_meta(key="ep_status.dw_processing.dw_id", value=episode.dw_id)
        case status.PUBLISHED_WITH_COUNTDOWN:
            return
        case status.PUBLISHED_FINAL:
            return
        case _:
            assert_never(status)
