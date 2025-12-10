# Load in all workers to make sure WireLoft knows about them
from .debug_ep_details import debug_ep_details
from .download_profile_worker import download_profile_worker
from .download_series_thumbnail import download_series_thumbnail
from .index_show_worker import index_show_worker
from .monitor_episode_worker import monitor_episode_worker
from .new_episode_finder import new_episode_finder

# Worker to test other workers
from .trigger_task_worker import trigger_task_worker