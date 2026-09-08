from __future__ import annotations

from importlib import import_module
from typing import Any


"""Task worker packages.

Concrete worker modules are loaded lazily. This preserves the historical
``task_manager.tasks.workers.<worker>`` exports without importing every worker
when one task helper or worker service is needed.
"""

_WORKER_EXPORTS = {
    "debug_ep_details": ".debug_ep_details",
    "download_episode": ".download_episode",
    "download_movie": ".download_movie",
    "refresh_movie_extras": ".refresh_movie_extras",
    "download_profile_worker": ".download_profile_worker",
    "download_series_thumbnail": ".download_series_thumbnail",
    "monitor_pending_episode": ".monitor_pending_episode",
    "fetch_new_episodes": ".fetch_new_episodes",
    "monitor_no_usable_media_episode": ".monitor_no_usable_media_episode",
    "refresh_episode_metadata": ".refresh_episode_metadata",
}


def __getattr__(name: str) -> Any:
    module_name = _WORKER_EXPORTS.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    worker = getattr(import_module(module_name, __name__), name)
    globals()[name] = worker
    return worker


__all__ = list(_WORKER_EXPORTS)
