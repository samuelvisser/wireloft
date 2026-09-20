from __future__ import annotations

from backend.db.background_migrations import run_pending_background_migrations
from task_manager.scheduler.registry import task
from task_manager.scheduler.results import TaskResult


@task(
    key="background_migration_runner",
    title="Background migrations",
    description="Applies required historical data migrations in version order.",
    allowed_resource_types=("system",),
    default_max_retries=3,
    tracks_progress=True,
    pauses_scheduled_work=True,
)
async def background_migration_runner(
    *,
    resource_id: int | None = None,
    progress=None,
) -> TaskResult:
    result = await run_pending_background_migrations(progress=progress)
    applied = len(result.applied_revisions)
    return TaskResult(
        summary=(
            "Background migrations are up to date"
            if applied == 0
            else f"Applied {applied} background {'migration' if applied == 1 else 'migrations'}"
        ),
        data={
            "applied": applied,
            "background_migration_revision": result.current_revision,
        },
    )
