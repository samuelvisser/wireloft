from task_manager.tasks.workers.refresh_episode_metadata import service as _service

MiddlewareClient = _service.MiddlewareClient
schedule_remaining_metadata_checks = _service.schedule_remaining_metadata_checks
remove_episode_metadata_jobs = _service.remove_episode_metadata_jobs
trigger_now = _service.trigger_now


async def run_refresh_episode_metadata_worker(*args, **kwargs):
    # Preserve monkeypatch compatibility for older imports while delegating all
    # actual lifecycle behavior to the renamed worker.
    _service.MiddlewareClient = MiddlewareClient
    _service.schedule_remaining_metadata_checks = schedule_remaining_metadata_checks
    _service.remove_episode_metadata_jobs = remove_episode_metadata_jobs
    _service.trigger_now = trigger_now
    return await _service.run_refresh_episode_metadata(*args, **kwargs)


__all__ = ["run_refresh_episode_metadata_worker"]
