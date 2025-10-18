from datetime import datetime, timezone, timedelta

from dailywire_api.records import EpisodeRecord
from wireloft_config import get_settings


def is_published_final(episode: EpisodeRecord):
    if not episode.publish_status == "PUBLISHED":
        return False

    return date_is_min_ago(episode.published_date, get_settings().final_ep_published_delay_minutes)


def date_is_min_ago(date, minutes: int) -> bool:
    if not date:
        return False
    now = datetime.now(timezone.utc)
    return (now - date) >= timedelta(minutes=minutes)