# Load in all workers to make sure WireLoft knows about them
from .debug_ep_details import debug_ep_details
from .download_episode import download_episode
from .download_movie import download_movie
from .refresh_movie_extras import refresh_movie_extras
from .download_profile_worker import download_profile_worker
from .download_series_thumbnail import download_series_thumbnail
from .monitor_episode_worker import monitor_episode_worker
from .fetch_new_episodes import fetch_new_episodes
from .cleanup_episodes_stuck_without_media import cleanup_episodes_stuck_without_media

# Worker to test other workers
from .trigger_task_worker import trigger_task_worker
