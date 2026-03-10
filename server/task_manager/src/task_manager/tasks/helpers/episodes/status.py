from __future__ import annotations

from backend.db.models import Episode as DbEpisode
from backend.types.episode_types import EpisodePublishStatus
from dailywire_api.records import DwEpisodeRecord as DwEpisode, DwEpisodeDetailRecord
from config import get_settings
from controller.m3u8 import get_vod_info
from task_manager.tasks.helpers.general import date_is_min_ago

def _get_publish_status_static(ep: DwEpisode) -> EpisodePublishStatus | None:
    if ep.publish_status.upper().__contains__("SCHEDULED"):
        return EpisodePublishStatus.SCHEDULED
    if ep.publish_status.upper().__contains__("LIVE"):
        return EpisodePublishStatus.LIVE
    if ep.slug.lower().__contains__("delayed-start"):
        return EpisodePublishStatus.DELAYED
    return None


def _can_assume_no_countdown(episode: DwEpisode | DbEpisode) -> bool:
    ep_dur_min = int(episode.duration / 60)

    # DW tends to return a very short ep duration when the episode is not yet processed
    if ep_dur_min < 1:
        ep_dur_min = 120
    return date_is_min_ago(episode.published_date, get_settings().episode_status_timing.published_final_after_minutes + ep_dur_min)


def is_published_final(episode: DwEpisode | DbEpisode):
    if _get_publish_status_static(episode) is not None:
        return False
    return _can_assume_no_countdown(episode)


def get_publish_status_from_dw_detail(dw_ep: DwEpisodeDetailRecord) -> EpisodePublishStatus:
    # Statuses we can get easily from DW
    static = _get_publish_status_static(dw_ep)
    if static is not None:
        return static

    # Hard cutoff to prevent the episode being forever not finished
    ep_dur_min = int(dw_ep.duration / 60)
    ep_pub_final = get_settings().episode_status_timing.published_final_after_minutes
    if date_is_min_ago(dw_ep.published_date, ep_pub_final + ep_dur_min):
        return EpisodePublishStatus.PUBLISHED_FINAL

    # If published but the duration is very short (usually 11.81 seconds), it's still processing
    vod_info = get_vod_info(dw_ep.video_url)
    if dw_ep.publish_status == "PUBLISHED" and dw_ep.duration < 12 < vod_info.seconds:
        return EpisodePublishStatus.DW_PROCESSING

    # As long as the episode is not marked downloadable, it still contains the countdown
    if not dw_ep.is_downloadable and not _can_assume_no_countdown(dw_ep):
        return EpisodePublishStatus.PUBLISHED_WITH_COUNTDOWN

    return EpisodePublishStatus.PUBLISHED_FINAL