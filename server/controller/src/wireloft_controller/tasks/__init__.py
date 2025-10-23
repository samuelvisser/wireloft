# Ensure task modules are imported so their definitions are registered
from wireloft_controller.tasks.workers.download_series_thumbnail import download_series_thumbnail  # noqa: F401
from . import workers  # noqa: F401
