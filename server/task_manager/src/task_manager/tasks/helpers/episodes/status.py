from __future__ import annotations

from backend.db.models import Episode as DbEpisode
from backend.types.episode_types import EpisodePublishStatus
from dailywire_api.records import DwEpisodeRecord as DwEpisode, DwEpisodeDetailRecord
from config import get_settings
from controller.m3u8 import get_vod_info
from task_manager.tasks.helpers.general import date_is_min_ago
from .no_show import is_no_show_today_title


def _get_publish_status_static(ep: DwEpisode) -> EpisodePublishStatus | None:
    if ep.publish_status.upper().__contains__("SCHEDULED"):
        return EpisodePublishStatus.SCHEDULED
    if ep.publish_status.upper().__contains__("LIVE"):
        return EpisodePublishStatus.LIVE
    if ep.slug.lower().__contains__("delayed-start"):
        return EpisodePublishStatus.DELAYED
    return None


def _published_final_cutoff_elapsed(episode: DwEpisode | DbEpisode) -> bool:
    """Whether WireLoft's absolute publication-final fallback has elapsed."""
    return date_is_min_ago(
        episode.published_date,
        get_settings().episode_status_timing.published_final_after_minutes,
    )


def is_published_final(episode: DwEpisode | DbEpisode):
    # A known placeholder is deliberately never considered usable media, even if
    # its timestamp is old enough to cross the normal final-publication fallback.
    if is_no_show_today_title(episode.title):
        return False

    # This setting is an absolute safety net. Once publishedAt is this old, stop
    # trusting stale Daily Wire lifecycle flags and treat the episode as final.
    return _published_final_cutoff_elapsed(episode)


def get_publish_status_from_dw_detail(dw_ep: DwEpisodeDetailRecord) -> EpisodePublishStatus:
    # "No Show Today" entries are placeholders, not playable episodes. Keeping
    # them in DW_PROCESSING makes all media eligibility logic treat them like any
    # other temporarily unusable Daily Wire item.
    if is_no_show_today_title(dw_ep.title):
        return EpisodePublishStatus.DW_PROCESSING

    # Hard cutoff to prevent stale or contradictory Daily Wire state from keeping
    # an episode pending forever. This intentionally ignores episode duration:
    # publishedFinalAfterMinutes is measured directly from publishedAt.
    if _published_final_cutoff_elapsed(dw_ep):
        return EpisodePublishStatus.PUBLISHED_FINAL

    # Statuses we can get easily from DW while still inside the fallback window.
    static = _get_publish_status_static(dw_ep)
    if static is not None:
        return static

    # If published but the duration is very short (usually 11.81 seconds), it's still processing
    vod_info = get_vod_info(dw_ep.video_url)
    if dw_ep.publish_status == "PUBLISHED" and dw_ep.duration < 12 < vod_info.seconds:
        return EpisodePublishStatus.DW_PROCESSING

    # As long as the episode is not marked downloadable, it still contains the countdown
    if not dw_ep.is_downloadable:
        return EpisodePublishStatus.PUBLISHED_WITH_COUNTDOWN

    return EpisodePublishStatus.PUBLISHED_FINAL
