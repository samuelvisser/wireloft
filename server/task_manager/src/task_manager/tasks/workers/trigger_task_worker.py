from __future__ import annotations

from task_manager.scheduler.executor import trigger_now as exec_trigger_now
from task_manager.scheduler.registry import task


@task(
    key="trigger_task_worker",
    title="Triggers task",
    description="Trigger task",
    allowed_resource_types=("show",),
    default_max_retries=5,
    tracks_progress=True,
)
async def trigger_task_worker(*, progress=None) -> None:

    exec_trigger_now(def_key="fetch_new_episodes", resource_type="show", resource_id=2)
