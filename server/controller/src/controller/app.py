from __future__ import annotations

import inspect
import logging
import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from typing import Any

from backend.db import get_session
from config import get_settings


logger = logging.getLogger(__name__)
_controller_started = False
_controller_lock = Lock()


@contextmanager
def db_session():
    session = get_session()
    try:
        yield session
    finally:
        session.close()


def _task_event_kwargs(task_key: str, event_data: dict[str, Any]) -> dict[str, Any]:
    """Keep event fields explicitly supported by the target worker."""
    from task_manager.scheduler.registry import get_task

    _, task_callable = get_task(task_key)
    signature = inspect.signature(task_callable)
    parameters = signature.parameters.values()
    if any(parameter.kind is inspect.Parameter.VAR_KEYWORD for parameter in parameters):
        return event_data

    accepted = {
        parameter.name
        for parameter in parameters
        if parameter.kind in (inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY)
    }
    accepted.difference_update({"resource_id", "progress"})
    return {key: value for key, value in event_data.items() if key in accepted}


def setup_triggers_from_registry() -> None:
    """Install code-defined cron jobs and event-to-task subscriptions."""
    from apscheduler.triggers.cron import CronTrigger
    from task_manager.events.registry import WireloftEventLinker
    from task_manager.scheduler.executor import execute_task, trigger_now as scheduler_trigger_now
    from task_manager.scheduler.registry import all_triggers
    from task_manager.scheduler.scheduler import start_scheduler

    if not get_settings().scheduler.enabled:
        return

    scheduler = start_scheduler()

    # Rebuilding subscriptions must be safe in reloads and repeated test lifecycles.
    WireloftEventLinker.remove_all()

    for task_key, triggers in all_triggers().items():
        for index, trigger in enumerate(triggers):
            if trigger.trigger_type == "cron":
                cron_trigger = CronTrigger.from_crontab(
                    trigger.cron,
                    timezone=get_settings().timezone,
                )
                job_id = f"auto-{task_key}-{trigger.resource_type}-{trigger.resource_id}-{index}"
                scheduler.add_job(
                    execute_task,
                    trigger=cron_trigger,
                    kwargs={
                        "def_key": task_key,
                        "resource_type": trigger.resource_type or "show",
                        "resource_id": trigger.resource_id if trigger.resource_id is not None else 0,
                        "schedule_id": None,
                    },
                    id=job_id,
                    replace_existing=True,
                    coalesce=trigger.coalesce,
                )
                continue

            if trigger.trigger_type != "event":
                logger.warning("Ignoring unsupported trigger type %s for %s", trigger.trigger_type, task_key)
                continue

            def create_event_handler(task_key_captured: str, resource_type_captured: str | None):
                def handler(**event_data: Any) -> None:
                    # resource_id=0 is meaningful, so do not use truthiness here.
                    resource_id = event_data.get("resource_id")
                    if resource_id is None:
                        resource_id = event_data.get("id")

                    forwarded_data = {
                        key: value
                        for key, value in event_data.items()
                        if key not in {"resource_id", "id"}
                    }
                    scheduler_trigger_now(
                        def_key=task_key_captured,
                        resource_type=resource_type_captured or "show",
                        resource_id=resource_id,
                        **_task_event_kwargs(task_key_captured, forwarded_data),
                    )

                return handler

            WireloftEventLinker.subscribe(
                trigger.event_name,
                event_callback=create_event_handler(task_key, trigger.resource_type),
            )


def _should_emit_startup_event() -> bool:
    """Whether this worker should fire ``app.startup`` (and its subscribed tasks).

    Normal runs always emit. Under ``--debug`` the reloader supervisor exports
    ``WIRELOFT_RELOAD_SUPERVISOR_PID`` to every worker subprocess it spawns; on
    each file change it kills the worker and spawns a fresh one, which would
    re-emit startup and re-trigger tasks. We guard with a marker file keyed to
    the supervisor pid: the first worker atomically creates it and emits; reload
    workers find it already present and skip. The supervisor removes the marker
    on exit (see ``backend.__main__``).
    """
    supervisor_pid = os.environ.get("WIRELOFT_RELOAD_SUPERVISOR_PID")
    if not supervisor_pid:
        return True

    marker = Path(tempfile.gettempdir()) / f"wireloft-reload-startup-{supervisor_pid}.lock"
    try:
        # O_CREAT | O_EXCL is atomic, so this is race-free across workers.
        os.close(os.open(marker, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        return True
    except FileExistsError:
        logger.info("Skipping app.startup event on reload (debug mode)")
        return False


def emit_startup_event() -> None:
    from task_manager.events.emitters import emit_event

    emit_event("app.startup", {})


def reload_user_schedules() -> None:
    """Reload active user-created schedules from SQLite into APScheduler."""
    from sqlalchemy import select
    from task_manager.scheduler.db import TaskDefinition, TaskSchedule
    from task_manager.scheduler.scheduler import schedule_job

    with db_session() as session:
        statement = (
            select(TaskSchedule, TaskDefinition)
            .join(TaskDefinition, TaskDefinition.id == TaskSchedule.definition_id)
            .where(TaskSchedule.active.is_(True))
        )

        count = 0
        for schedule, definition in session.execute(statement):
            try:
                schedule_job(
                    schedule_id=schedule.id,
                    def_key=definition.key,
                    resource_type=schedule.resource_type,
                    resource_id=schedule.resource_id,
                    trigger=schedule.trigger,
                    trigger_args=schedule.trigger_args,
                )
                count += 1
            except Exception:
                logger.exception("Failed to reload schedule %s", schedule.id)

        if count:
            logger.info("Reloaded %s user-created schedule(s)", count)


def start_controller() -> None:
    """Start task registration, scheduler jobs, and event subscriptions once."""
    global _controller_started

    with _controller_lock:
        if _controller_started:
            return

        try:
            # Import workers so their decorators populate the registry.
            import task_manager.tasks  # noqa: F401
            from task_manager.scheduler.registry import sync_registry_to_db
            from task_manager.scheduler.scheduler import start_scheduler

            if get_settings().scheduler.enabled:
                sync_registry_to_db()
                start_scheduler()
                reload_user_schedules()
                setup_triggers_from_registry()
                if _should_emit_startup_event():
                    emit_startup_event()

            _controller_started = True
        except Exception:
            # Startup is atomic from the application's perspective. Clean up any
            # scheduler/event state created before the failure, then fail fast.
            from task_manager.events.registry import WireloftEventLinker, shutdown_event_emitter
            from task_manager.scheduler.scheduler import shutdown_scheduler

            WireloftEventLinker.remove_all()
            shutdown_scheduler(wait=False)
            shutdown_event_emitter()
            _controller_started = False
            raise


def stop_controller() -> None:
    """Drain domain events, stop scheduling, and reset all lifecycle state."""
    global _controller_started

    with _controller_lock:
        if not _controller_started:
            return

        from task_manager.events.registry import (
            WireloftEventLinker,
            shutdown_event_emitter,
            wait_for_events,
        )
        from task_manager.scheduler.scheduler import shutdown_scheduler

        WireloftEventLinker.remove_all()
        wait_for_events()
        shutdown_scheduler(wait=True)
        shutdown_event_emitter()
        _controller_started = False


# Backwards-compatible entrypoint used by older imports.
app = start_controller
