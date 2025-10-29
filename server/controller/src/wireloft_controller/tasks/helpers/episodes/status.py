from __future__ import annotations

from typing import Optional

from backend.db.models import Episode as DbEpisode
from backend.types.episode_types import EpisodePublishStatus
from dailywire_api.records import DwEpisodeRecord as DwEpisode
from wireloft_config import get_settings
from wireloft_controller.tasks.helpers.general import date_is_min_ago


def is_published_final(episode: DwEpisode | DbEpisode):
    if not episode.publish_status == "PUBLISHED":
        return False

    ep_dur_min = int(episode.duration / 60)

    # DW tends to return a very short ep duration when the episode is not yet processed
    if ep_dur_min < 1:
        ep_dur_min = 120
    return date_is_min_ago(episode.published_date, get_settings().episode_status_timing.published_final_after_minutes + ep_dur_min)


def get_publish_status_from_dw(dw_ep: DwEpisode, db_ep: Optional[DbEpisode]) -> EpisodePublishStatus:
    if is_published_final(dw_ep):
        return EpisodePublishStatus.PUBLISHED_FINAL
    if dw_ep.publish_status == "SCHEDULED":
        return EpisodePublishStatus.SCHEDULED
    if dw_ep.publish_status == "LIVE":
        return EpisodePublishStatus.LIVE
    if "delayed-start" in dw_ep.slug:
        return EpisodePublishStatus.DELAYED

    if db_ep is not None:
        # With db episode we can try to get ep status very accurately
        dw_id_while_live = db_ep.meta_items.get("ep_status.live.dw_id", None)
        if dw_id_while_live is not None and dw_id_while_live == dw_ep.dw_id:
            # if dw reports the episode is published, but its id is the same as when it was live, it means it's still processing and not available for download yet
            return EpisodePublishStatus.DW_PROCESSING
        # TODO we need some more analysis to reliably distinguish between published with countdown and final

    # Could not determine status based on db tracing. Guess based on timing
    ep_dur_min = int(dw_ep.duration / 60)
    if ep_dur_min < 1:
        ep_dur_min = 120
    ep_pub_countdown = get_settings().episode_status_timing.published_countdown_after_minutes
    ep_pub_final = get_settings().episode_status_timing.published_final_after_minutes

    if not date_is_min_ago(dw_ep.published_date, ep_pub_countdown + ep_dur_min):
        return EpisodePublishStatus.DW_PROCESSING
    if date_is_min_ago(dw_ep.published_date, ep_pub_final + ep_dur_min):
        return EpisodePublishStatus.PUBLISHED_FINAL
    return EpisodePublishStatus.PUBLISHED_WITH_COUNTDOWN
