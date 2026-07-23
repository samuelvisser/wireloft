from __future__ import annotations

"""
WireLoft Task Manager - Task scheduling and event management.

Provides:
- Task workers for background processing
- SQLAlchemy models to track task definitions, schedules, and runs
- Task registry and decorators to register workers (@task, @on_cron, @on_event)
- Execution wrapper that records progress and supports retries
- APScheduler lifecycle management
- Event-driven task triggering via pyventus

Public entrypoints:
- task_manager.scheduler.scheduler.start_scheduler()
- task_manager.scheduler.scheduler.schedule_job(...)
- task_manager.scheduler.executor.trigger_now(...)
- task_manager.events.registry.get_wireloft_event_emitter()
- task_manager.events.emitters.emit_*() functions

Note: This package expects the main app to have configured the database via backend.db.configure_db().
"""

# Subpackages are intentionally not imported here. Importing task_manager must be
# side-effect free; the controller imports task_manager.tasks during app startup
# when task registration is actually required.
