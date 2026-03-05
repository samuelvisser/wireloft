"""WireLoft Controller

Registers task definitions and provides helpers for implementing controller tasks.

Importing this package will import all built-in task definitions so that
wireloft_motherboard.scheduler.registry.sync_registry_to_db() can discover them.
"""

# Import tasks so their @task decorators run at import time
from . import tasks  # noqa: F401
from . import app
from .app import app