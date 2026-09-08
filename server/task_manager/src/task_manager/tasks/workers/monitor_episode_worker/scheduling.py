from task_manager.tasks.workers.monitor_pending_episode import scheduling as _scheduling


MONITOR_REQUESTED_EVENT = _scheduling.MONITOR_REQUESTED_EVENT
MONITOR_COMPLETED_EVENT = _scheduling.MONITOR_COMPLETED_EVENT
start_scheduler = _scheduling.start_scheduler
get_settings = _scheduling.get_settings
queue_event = _scheduling.queue_event


def _compat_settings():
    settings = get_settings()
    schedule = settings.new_episode_schedule
    if not hasattr(schedule, "monitor_pending_episode_cron") and hasattr(schedule, "monitor_episode_cron"):
        schedule.monitor_pending_episode_cron = schedule.monitor_episode_cron
    return settings


def monitor_job_id(resource_id: int) -> str:
    return _scheduling.monitor_job_id(resource_id)


def schedule_episode_monitor(*, resource_id: int) -> str:
    _scheduling.start_scheduler = start_scheduler
    _scheduling.get_settings = _compat_settings
    return _scheduling.schedule_episode_monitor(resource_id=resource_id)


def remove_episode_monitor(*, resource_id: int) -> None:
    _scheduling.start_scheduler = start_scheduler
    return _scheduling.remove_episode_monitor(resource_id=resource_id)


def queue_monitor_completion_if_settled(*args, **kwargs):
    _scheduling.queue_event = queue_event
    return _scheduling.queue_monitor_completion_if_settled(*args, **kwargs)


def register_monitor_event_handlers() -> None:
    _scheduling.start_scheduler = start_scheduler
    _scheduling.get_settings = _compat_settings
    _scheduling.queue_event = queue_event
    return _scheduling.register_monitor_event_handlers()


__all__ = [
    "MONITOR_REQUESTED_EVENT",
    "MONITOR_COMPLETED_EVENT",
    "monitor_job_id",
    "schedule_episode_monitor",
    "remove_episode_monitor",
    "queue_monitor_completion_if_settled",
    "register_monitor_event_handlers",
]
