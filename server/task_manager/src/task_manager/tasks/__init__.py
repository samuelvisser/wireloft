from __future__ import annotations

from importlib import import_module
from typing import Any


# Importing a helper beneath task_manager.tasks must not initialize every worker.
# Backend API services use task helpers during router construction, while some
# workers legitimately import backend services. Eager worker registration here
# therefore creates circular imports purely from package initialization order.
_WORKER_EXPORTS = {
    "debug_ep_details": ".workers.debug_ep_details",
    "download_episode": ".workers.download_episode",
    "download_movie": ".workers.download_movie",
    "refresh_movie_extras": ".workers.refresh_movie_extras",
    "download_profile_worker": ".workers.download_profile_worker",
    "download_series_thumbnail": ".workers.download_series_thumbnail",
    "monitor_pending_episode": ".workers.monitor_pending_episode",
    "refresh_episode_metadata": ".workers.refresh_episode_metadata",
    "rename_file_worker": ".workers.rename_file_worker",
    "redownload_show_episodes_worker": ".workers.redownload_show_episodes_worker",
    "fetch_new_episodes": ".workers.fetch_new_episodes",
    "monitor_no_usable_media_episode": ".workers.monitor_no_usable_media_episode",
    "file_watcher": ".workers.file_watcher",
    "trigger_task_worker": ".workers.trigger_task_worker",
}


def _load_worker(name: str) -> Any:
    module_name = _WORKER_EXPORTS[name]
    worker = getattr(import_module(module_name, __name__), name)
    globals()[name] = worker
    return worker


def load_all_tasks() -> None:
    """Import every worker so its decorators populate the task registry.

    Registration is intentionally explicit. Importing a task helper can load the
    helper (and, for a worker subpackage, that worker) without recursively loading
    unrelated workers. Controller startup and the CLI call this function before
    they rely on the complete registry.
    """
    for name in _WORKER_EXPORTS:
        _load_worker(name)


def __getattr__(name: str) -> Any:
    """Preserve the historical task_manager.tasks.<worker> public imports lazily."""
    if name in _WORKER_EXPORTS:
        return _load_worker(name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["load_all_tasks", *_WORKER_EXPORTS]
