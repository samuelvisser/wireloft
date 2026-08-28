# Import all workers to ensure they are registered
from .workers.debug_ep_details import debug_ep_details
from .workers.resume_interrupted_downloads import resume_interrupted_downloads
from .workers.download_profile_worker import download_profile_worker
from .workers.download_series_thumbnail import download_series_thumbnail
from .workers.monitor_episode_worker import monitor_episode_worker
from .workers.fetch_new_episodes import fetch_new_episodes
from .workers.check_no_show_today_episodes import check_no_show_today_episodes
from .workers.file_watcher import file_watcher
from .workers.trigger_task_worker import trigger_task_worker

__all__ = [
    "debug_ep_details",
    "resume_interrupted_downloads",
    "download_profile_worker",
    "download_series_thumbnail",
    "monitor_episode_worker",
    "fetch_new_episodes",
    "check_no_show_today_episodes",
    "file_watcher",
    "trigger_task_worker",
]
