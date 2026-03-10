from __future__ import annotations

from contextlib import contextmanager

from backend.db import get_session
from config import get_settings

_controller_initiated = False


@contextmanager
def db_session():
    s = get_session()
    try:
        yield s
    finally:
        s.close()


def setup_triggers_from_registry() -> None:
    """Set up all cron and event triggers from the task registry."""
    from apscheduler.triggers.cron import CronTrigger
    from pyventus.events import EventLinker
    from task_manager.scheduler.executor import execute_task, trigger_now as scheduler_trigger_now
    from task_manager.scheduler.scheduler import start_scheduler
    from task_manager.scheduler.registry import all_triggers

    if not get_settings().scheduler.enabled:
        return

    sch = start_scheduler()

    # Get all triggers from the registry
    all_task_triggers = all_triggers()

    for task_key, triggers in all_task_triggers.items():
        for idx, trigger in enumerate(triggers):
            if trigger.trigger_type == "cron":
                # Use cron expression directly (no more settings resolution)
                cron_expr = trigger.cron

                # Create APScheduler job
                cron_trigger = CronTrigger.from_crontab(cron_expr, timezone=get_settings().timezone)
                job_id = f"auto-{task_key}-{trigger.resource_type}-{trigger.resource_id}-{idx}"

                sch.add_job(
                    execute_task,
                    trigger=cron_trigger,
                    kwargs=dict(
                        def_key=task_key,
                        resource_type=trigger.resource_type or "show",
                        resource_id=trigger.resource_id if trigger.resource_id is not None else 0,
                        schedule_id=None,
                    ),
                    id=job_id,
                    replace_existing=True,
                    coalesce=trigger.coalesce,
                )

            elif trigger.trigger_type == "event":
                # Register event listener
                event_name = trigger.event_name

                # Create handler that triggers the task
                def create_event_handler(task_key_captured, resource_type_captured):
                    async def handler(**kwargs):
                        # Extract resource_id from kwargs if available
                        resource_id = kwargs.get("resource_id") or kwargs.get("id")

                        # Trigger the task
                        scheduler_trigger_now(
                            def_key=task_key_captured,
                            resource_type=resource_type_captured or "show",
                            resource_id=resource_id,
                        )
                    return handler

                # Register the handler using EventLinker decorator
                handler = create_event_handler(task_key, trigger.resource_type)
                EventLinker.on(event_name)(handler)


def emit_startup_event():
    """Emit the app.startup event to trigger startup tasks."""
    from task_manager.events.emitters import emit_event
    emit_event("app.startup", {})


def app():
    global _controller_initiated

    if _controller_initiated:
        return

    # Start scheduler and sync task registry if enabled
    try:
        # Ensure motherboard tasks are imported so they are registered
        import task_manager.tasks  # noqa: F401
        from task_manager.scheduler.scheduler import start_scheduler
        from task_manager.scheduler.registry import sync_registry_to_db

        if get_settings().scheduler.enabled:
            # Sync task definitions to database
            sync_registry_to_db()

            # Start the APScheduler instance
            start_scheduler()

            # Set up all cron and event triggers from the registry
            try:
                setup_triggers_from_registry()
            except (ValueError, KeyError, ImportError, AttributeError) as e:
                # Log but don't crash if auto-scheduling fails
                import sys
                print(f"Warning: Failed to setup some triggers: {e}", file=sys.stderr)

            # Emit startup event to trigger startup tasks
            try:
                emit_startup_event()
            except Exception as e:
                import sys
                print(f"Warning: Failed to emit startup event: {e}", file=sys.stderr)

    except (AttributeError, RuntimeError, ImportError) as e:
        # Do not crash app if scheduler initialization or registry sync fails
        import sys
        print(f"Warning: Failed to initialize scheduler: {e}", file=sys.stderr)

    _controller_initiated = True
