# Load in all workers to make sure WireLoft knows about them
from .debug_ep_details import debug_ep_details
from .download_episode import download_episode
from .download_movie import download_movie
from .refresh_movie_extras import refresh_movie_extras
from .download_profile_worker import (
    download_profile_identifier_change_worker,
    download_profile_worker,
)
from .download_series_thumbnail import download_series_thumbnail
from .monitor_pending_episode import monitor_pending_episode
from .fetch_new_episodes import fetch_new_episodes
from .monitor_no_usable_media_episode import monitor_no_usable_media_episode
from .refresh_episode_metadata import refresh_episode_metadata

# Worker to test other workers
from .trigger_task_worker import trigger_task_worker
