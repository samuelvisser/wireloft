from __future__ import annotations

from contextlib import contextmanager

from backend.db import get_session
from wireloft_config import get_settings

_controller_initiated = False


@contextmanager
def db_session():
    s = get_session()
    try:
        yield s
    finally:
        s.close()


def _resolve_cron_from_settings(cron_spec: str) -> str:
    """Resolve a cron spec from settings if it starts with 'settings:'"""
    if not cron_spec.startswith("settings:"):
        return cron_spec

    # Extract the settings path
    path = cron_spec[9:]  # Remove "settings:" prefix
    parts = path.split(".")

    # Navigate through settings
    value = get_settings()
    for part in parts:
        value = getattr(value, part)

    # If it's an interval in minutes, convert to cron expression
    if isinstance(value, int):
        # Assume it's minutes, convert to cron: */N * * * *
        return f"*/{value} * * * *"

    return str(value)


def setup_triggers_from_registry() -> None:
    """Set up all cron and event triggers from the task registry."""
    from apscheduler.triggers.cron import CronTrigger
    from wireloft_motherboard.scheduler.executor import execute_task, trigger_now as scheduler_trigger_now
    from wireloft_motherboard.scheduler.scheduler import start_scheduler
    from wireloft_motherboard.scheduler.registry import all_triggers
    from wireloft_motherboard.events.registry import get_wireloft_event_emitter

    if not get_settings().scheduler.enabled:
        return

    sch = start_scheduler()
    event_emitter = get_wireloft_event_emitter()

    # Get all triggers from the registry
    all_task_triggers = all_triggers()

    for task_key, triggers in all_task_triggers.items():
        for idx, trigger in enumerate(triggers):
            if trigger.trigger_type == "cron":
                # Resolve cron from settings if needed
                cron_expr = _resolve_cron_from_settings(trigger.cron)

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

                # If run_on_startup is True, trigger immediately
                if trigger.run_on_startup:
                    scheduler_trigger_now(
                        def_key=task_key,
                        resource_type=trigger.resource_type or "show",
                        resource_id=trigger.resource_id if trigger.resource_id is not None else 0,
                    )

            elif trigger.trigger_type == "event":
                # Register event listener
                event_name = trigger.event_name

                # Create handler that triggers the task
                def create_event_handler(task_key_captured, resource_type_captured):
                    async def handler(event_data=None, **kwargs):
                        # Extract resource_id from event data if available
                        resource_id = None
                        if isinstance(event_data, dict):
                            resource_id = event_data.get("resource_id") or event_data.get("id")
                        elif hasattr(event_data, "id"):
                            resource_id = event_data.id

                        # Trigger the task
                        scheduler_trigger_now(
                            def_key=task_key_captured,
                            resource_type=resource_type_captured or "show",
                            resource_id=resource_id,
                        )
                    return handler

                # Register the handler
                handler = create_event_handler(task_key, trigger.resource_type)
                event_emitter.on(event_name, handler)


def app():
    global _controller_initiated

    if _controller_initiated:
        return

    # Start scheduler and sync task registry if enabled
    try:
        # Ensure controller tasks are imported so they are registered
        from wireloft_motherboard.scheduler.scheduler import start_scheduler
        from wireloft_motherboard.scheduler.registry import sync_registry_to_db

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
    except (AttributeError, RuntimeError, ImportError) as e:
        # Do not crash app if scheduler initialization or registry sync fails
        import sys
        print(f"Warning: Failed to initialize scheduler: {e}", file=sys.stderr)

    _controller_initiated = True
