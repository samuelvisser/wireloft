# Import all workers to ensure they are registered
from .workers.debug_ep_details import debug_ep_details
from .workers.download_episode import download_episode
from .workers.download_movie import download_movie
from .workers.refresh_movie_extras import refresh_movie_extras
from .workers.download_profile_worker import (
    download_profile_identifier_change_worker,
    download_profile_worker,
)
from .workers.download_series_thumbnail import download_series_thumbnail
from .workers.monitor_pending_episode import monitor_pending_episode
from .workers.refresh_episode_metadata import refresh_episode_metadata
from .workers.redownload_show_episodes_worker import redownload_show_episodes_worker
from .workers.fetch_new_episodes import fetch_new_episodes
from .workers.monitor_no_usable_media_episode import monitor_no_usable_media_episode
from .workers.file_watcher import file_watcher
from .workers.trigger_task_worker import trigger_task_worker

__all__ = [
    "debug_ep_details",
    "download_episode",
    "download_movie",
    "refresh_movie_extras",
    "download_profile_worker",
    "download_profile_identifier_change_worker",
    "download_series_thumbnail",
    "monitor_pending_episode",
    "refresh_episode_metadata",
    "redownload_show_episodes_worker",
    "fetch_new_episodes",
    "monitor_no_usable_media_episode",
    "file_watcher",
    "trigger_task_worker",
]
