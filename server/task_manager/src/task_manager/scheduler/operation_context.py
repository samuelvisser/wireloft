from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterable, Iterator


_current_operation_ids: ContextVar[tuple[str, ...]] = ContextVar(
    "wireloft_task_operation_ids",
    default=(),
)


def current_operation_ids() -> tuple[str, ...]:
    return _current_operation_ids.get()


@contextmanager
def operation_context(operation_ids: Iterable[str]) -> Iterator[None]:
    normalized = tuple(dict.fromkeys(str(value) for value in operation_ids if value))
    token = _current_operation_ids.set(normalized)
    try:
        yield
    finally:
        _current_operation_ids.reset(token)
