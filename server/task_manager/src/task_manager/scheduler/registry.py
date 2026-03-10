from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Awaitable, Optional, Dict, Tuple, List

from backend.db.core import get_session
from sqlalchemy import select

from task_manager.scheduler.db import TaskDefinition

_REGISTRY: Dict[str, Tuple[TaskMeta, Callable[..., Awaitable[None]]]] = {}


@dataclass
class TriggerMeta:
    """Metadata for a task trigger."""
    trigger_type: str  # 'cron', 'event'
    cron: Optional[str] = None  # For cron triggers (actual cron expression)
    event_name: Optional[str] = None  # For event triggers
    resource_type: Optional[str] = None  # Resource type for the trigger
    resource_id: Optional[int] = None  # Resource ID (0 = global, None = passed via event)
    coalesce: bool = True  # Whether to coalesce multiple pending jobs


@dataclass
class TaskMeta:
    key: str
    title: str
    description: str = ""
    allowed_resource_types: tuple[str, ...] = ("show", "season", "episode", "movie")
    default_max_retries: Optional[int] = None
    tracks_progress: bool = True
    triggers: List[TriggerMeta] = field(default_factory=list)


def task(
    key: str,
    title: str,
    description: str = "",
    allowed_resource_types: Optional[tuple[str, ...]] = None,
    default_max_retries: Optional[int] = None,
    tracks_progress: bool = True,
):
    """Decorator to register an async task callable.

    The callable signature should be: async def fn(resource_id: int, progress: ProgressUpdater, **kwargs)
    """

    def decorator(fn: Callable[..., Awaitable[None]]):
        meta = TaskMeta(
            key=key,
            title=title,
            description=description,
            allowed_resource_types=allowed_resource_types
            or ("show", "season", "episode", "movie"),
            default_max_retries=default_max_retries,
            tracks_progress=tracks_progress,
        )
        _REGISTRY[key] = (meta, fn)

        # Allow chaining with trigger decorators
        fn._task_meta = meta
        return fn

    return decorator


def on_cron(cron: str, resource_type: str = "show", resource_id: int = 0, coalesce: bool = True):
    """Decorator to add a cron-based trigger to a task.

    Args:
        cron: Cron expression (e.g., "*/30 * * * *") - must be actual value, not a settings reference
        resource_type: Resource type to run on
        resource_id: Resource ID to run on (0 for global)
        coalesce: Whether to coalesce multiple pending jobs
    """
    def decorator(fn: Callable[..., Awaitable[None]]):
        if not hasattr(fn, '_task_meta'):
            raise ValueError(f"@on_cron must be used after @task decorator")

        trigger = TriggerMeta(
            trigger_type='cron',
            cron=cron,
            resource_type=resource_type,
            resource_id=resource_id,
            coalesce=coalesce,
        )
        fn._task_meta.triggers.append(trigger)
        return fn

    return decorator


def on_event(event_name: str, resource_type: Optional[str] = None):
    """Decorator to add an event-based trigger to a task.

    Args:
        event_name: Name of the event to listen for (e.g., "show.added", "episode.published_final")
        resource_type: Optional resource type filter
    """
    def decorator(fn: Callable[..., Awaitable[None]]):
        if not hasattr(fn, '_task_meta'):
            raise ValueError(f"@on_event must be used after @task decorator")

        trigger = TriggerMeta(
            trigger_type='event',
            event_name=event_name,
            resource_type=resource_type,
        )
        fn._task_meta.triggers.append(trigger)
        return fn

    return decorator




def get_task(key: str) -> Tuple[TaskMeta, Callable[..., Awaitable[None]]]:
    return _REGISTRY[key]


def all_definitions() -> list[TaskMeta]:
    return [meta for meta, _ in _REGISTRY.values()]


def all_triggers() -> Dict[str, List[TriggerMeta]]:
    """Get all triggers organized by task key."""
    return {key: meta.triggers for key, (meta, _) in _REGISTRY.items() if meta.triggers}


def sync_registry_to_db() -> None:
    """Ensure TaskDefinition rows exist for all registry tasks."""
    session = get_session()
    try:
        existing = {
            row[0]: row[1]
            for row in session.execute(select(TaskDefinition.key, TaskDefinition.id)).all()
        }
        for meta, _ in _REGISTRY.values():
            if meta.key not in existing:
                td = TaskDefinition(
                    key=meta.key,
                    title=meta.title,
                    description=meta.description,
                    allowed_resource_types=list(meta.allowed_resource_types),
                    default_max_retries=meta.default_max_retries,
                )
                session.add(td)
        session.commit()
    finally:
        session.close()