from task_manager.tasks.helpers.episodes.status import EpisodeRemoteSnapshot, get_publish_status_from_dw_detail
from task_manager.tasks.workers.monitor_pending_episode import scheduling as _pending_scheduling
from task_manager.tasks.workers.monitor_pending_episode import service as _service
from . import scheduling as _legacy_scheduling


MiddlewareClient = _service.MiddlewareClient
_try_reconcile_slug_after_404 = _service._try_reconcile_slug_after_404


async def run_monitor_episode_worker(*args, **kwargs):
    """Legacy import adapter for the renamed pending worker."""
    _service.MiddlewareClient = MiddlewareClient
    _service._try_reconcile_slug_after_404 = _try_reconcile_slug_after_404
    _pending_scheduling.queue_event = _legacy_scheduling.queue_event

    def compatibility_resolver(detail, **_kwargs):
        return EpisodeRemoteSnapshot(
            status=get_publish_status_from_dw_detail(detail),
            has_usable_media=True,
        )

    original_resolver = _service.resolve_episode_status
    _service.resolve_episode_status = compatibility_resolver
    try:
        return await _service.run_monitor_pending_episode(*args, **kwargs)
    finally:
        _service.resolve_episode_status = original_resolver


__all__ = ["run_monitor_episode_worker"]
