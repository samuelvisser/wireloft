# Load in all workers to make sure WireLoft knows about them
from .debug_ep_details import debug_ep_details
from .download_episode import download_episode
from .download_movie import download_movie
from .resume_interrupted_downloads import resume_interrupted_downloads
from .download_profile_worker import download_profile_worker
from .download_series_thumbnail import download_series_thumbnail
from .monitor_episode_worker import monitor_episode_worker
from .fetch_new_episodes import fetch_new_episodes
from .check_no_show_today_episodes import check_no_show_today_episodes

# Worker to test other workers
from .trigger_task_worker import trigger_task_worker
