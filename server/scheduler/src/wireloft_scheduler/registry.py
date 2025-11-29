from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Awaitable, Optional, Dict, Tuple

from backend.db.core import get_session
from sqlalchemy import select

from wireloft_scheduler.db import TaskDefinition


@dataclass
class TaskMeta:
    key: str
    title: str
    description: str = ""
    allowed_resource_types: tuple[str, ...] = ("show", "season", "episode", "movie")
    default_max_retries: Optional[int] = None
    tracks_progress: bool = True


_REGISTRY: Dict[str, Tuple[TaskMeta, Callable[..., Awaitable[None]]]] = {}

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
        return fn

    return decorator


def get_task(key: str) -> Tuple[TaskMeta, Callable[..., Awaitable[None]]]:
    return _REGISTRY[key]


def all_definitions() -> list[TaskMeta]:
    return [meta for meta, _ in _REGISTRY.values()]


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