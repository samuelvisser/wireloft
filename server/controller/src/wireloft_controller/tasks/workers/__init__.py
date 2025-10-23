# Load in all workers to make sure WireLoft knows about them
from .index_show_worker import index_show_worker
from .download_series_thumbnail import download_series_thumbnail
from .new_episode_finder import new_episode_finder

# Worker to test other workers
from .trigger_task_worker import trigger_task_worker