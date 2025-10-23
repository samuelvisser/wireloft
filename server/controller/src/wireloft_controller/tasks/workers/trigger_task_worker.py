from typing import Optional

from wireloft_controller.tasks.registry import task
from wireloft_scheduler.executor import trigger_now as exec_trigger_now


@task(
    key="trigger_task_worker",
    title="Triggers task",
    description="Trigger task",
    allowed_resource_types=("show",),
    default_max_retries=5,
    tracks_progress=True,
)
async def trigger_task_worker(*, resource_id: Optional[int] = None, show_slug: Optional[str] = None, progress=None) -> None:

    exec_trigger_now(def_key="index_show_worker", resource_type="show", resource_id=2)
