from typing import Dict, Any

from dailywire_api.records import DwEpisodeRecord


def check_duplicate_episodes(episodes: list[DwEpisodeRecord], params: Dict[str, Any]) -> bool:
    """
    Check if any episodes are duplicates based on the last episode ID from params.
    """
    last_ep_id = params.get('lastShowEpisodeId') or params.get('lastPodcastEpisodeId')
    if last_ep_id and last_ep_id.strip():
        return any(ep.dw_id == last_ep_id for ep in episodes)
    return False