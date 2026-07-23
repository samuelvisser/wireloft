# Import all workers to ensure they are registered
from .workers.debug_ep_details import debug_ep_details
from .workers.download_profile_worker import download_profile_worker
from .workers.download_series_thumbnail import download_series_thumbnail
from .workers.monitor_episode_worker import monitor_episode_worker
from .workers.fetch_new_episodes import fetch_new_episodes
from .workers.file_watcher import file_watcher
from .workers.trigger_task_worker import trigger_task_worker

__all__ = [
    "debug_ep_details",
    "download_profile_worker",
    "download_series_thumbnail",
    "monitor_episode_worker",
    "fetch_new_episodes",
    "file_watcher",
    "trigger_task_worker",
]
