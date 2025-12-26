from __future__ import annotations

"""
WireLoft internal scheduler package.

Provides:
- SQLAlchemy models to track task definitions, schedules, and runs.
- A task registry and decorator to register internal tasks.
- An execution wrapper that records progress and supports retries.
- APScheduler lifecycle management wired into the backend app.

Public entrypoints:
- wireloft_scheduler.scheduler.start_scheduler()
- wireloft_scheduler.scheduler.schedule_job(...)
- wireloft_scheduler.executor.trigger_now(...)

Note: This package expects the main app to have configured the database via backend.db.configure_db().
"""

from .scheduler import db as _models
