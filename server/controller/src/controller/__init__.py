"""WireLoft Controller

Provides application initialization and lifecycle management.
Also contains shared utilities (db_utils, m3u8, util).

Tasks are managed by task_manager package.
"""

from . import app
from .app import app

__all__ = ["app"]