from __future__ import annotations

from wireloft_scheduler.executor import trigger_now as exec_trigger_now
from wireloft_scheduler.registry import task


@task(
    key="trigger_task_worker",
    title="Triggers task",
    description="Trigger task",
    allowed_resource_types=("show",),
    default_max_retries=5,
    tracks_progress=True,
)
async def trigger_task_worker(*, progress=None) -> None:

    exec_trigger_now(def_key="index_show_worker", resource_type="show", resource_id=2)
