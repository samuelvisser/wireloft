from task_manager.tasks.workers.monitor_no_usable_media_episode import service as _service


DEFAULT_STUCK_WITHOUT_MEDIA_DELETE_AFTER_MINUTES = (
    _service.DEFAULT_NO_USABLE_MEDIA_DELETE_AFTER_MINUTES
)
MiddlewareClient = _service.MiddlewareClient
DeviceAuthClient = _service.DeviceAuthClient


async def run_cleanup_episodes_stuck_without_media(*args, **kwargs):
    """Legacy import adapter for the renamed no-usable-media monitor."""
    _service.MiddlewareClient = MiddlewareClient
    _service.DeviceAuthClient = DeviceAuthClient
    return await _service.run_monitor_no_usable_media_episode(*args, **kwargs)


__all__ = [
    "DEFAULT_STUCK_WITHOUT_MEDIA_DELETE_AFTER_MINUTES",
    "run_cleanup_episodes_stuck_without_media",
]
