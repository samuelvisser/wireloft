from __future__ import annotations

from backend.db.models import Episode as DbEpisode
from dailywire_api.records import DwEpisodeRecord as DwEpisode
from wireloft_config import get_settings
from wireloft_controller.tasks.helpers.general import date_is_min_ago


def is_published_final(episode: DwEpisode | DbEpisode):
    if not episode.publish_status == "PUBLISHED":
        return False

    ep_dur_min = int(episode.duration / 60)
    return date_is_min_ago(episode.published_date, get_settings().final_ep_published_delay_minutes + ep_dur_min)