from __future__ import annotations

"""
Thin wrapper around wireloft_scheduler.registry to define controller tasks with
clear capability flags and defaults.

Usage:

from wireloft_controller.registry import task

@task(
    key="example",
    title="Example Task",
    description="Demo",
    allowed_resource_types=("download_profile_series",),
    default_max_retries=3,
    tracks_progress=False,
)
async def example(resource_id: int, progress):
    ...
"""

from dataclasses import dataclass
from typing import Optional, Callable, Awaitable

from wireloft_scheduler.registry import task as scheduler_task, TaskMeta as _SchedulerTaskMeta


@dataclass
class TaskCapabilities:
    """Capabilities exposed by a controller task."""
    default_max_retries: Optional[int] = None
    tracks_progress: bool = True


def task(
    *,
    key: str,
    title: str,
    description: str = "",
    allowed_resource_types: Optional[tuple[str, ...]] = None,
    default_max_retries: Optional[int] = None,
    tracks_progress: bool = True,
) -> Callable[[Callable[..., Awaitable[None]]], Callable[..., Awaitable[None]]]:
    """Register a task with scheduler, capturing controller-centric capabilities.

    This simply forwards to wireloft_scheduler.registry.task, but keeps a clear
    surface in the controller package for defining tasks.
    """

    return scheduler_task(
        key=key,
        title=title,
        description=description,
        allowed_resource_types=allowed_resource_types,
        default_max_retries=default_max_retries,
        tracks_progress=tracks_progress,
    )
