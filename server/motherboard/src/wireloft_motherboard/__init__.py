from __future__ import annotations

"""
WireLoft Motherboard - Central scheduling and event management.

Provides:
- SQLAlchemy models to track task definitions, schedules, and runs.
- A task registry and decorator to register internal tasks.
- An execution wrapper that records progress and supports retries.
- APScheduler lifecycle management wired into the backend app.
- Event-driven task triggering via pyventus.

Public entrypoints:
- wireloft_motherboard.scheduler.scheduler.start_scheduler()
- wireloft_motherboard.scheduler.scheduler.schedule_job(...)
- wireloft_motherboard.scheduler.executor.trigger_now(...)
- wireloft_motherboard.events.registry.get_wireloft_event_emitter()

Note: This package expects the main app to have configured the database via backend.db.configure_db().
"""

from .scheduler import scheduler as scheduler
from .scheduler import db as _models
