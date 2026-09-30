"""Scoped cancellation and retry reporting for every downloader HTTP request."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Callable, Iterator


@dataclass(frozen=True)
class TransferWait:
    reason: str
    until: float | None = None


cancel_check: ContextVar[Callable[[], bool] | None] = ContextVar("download_cancel", default=None)
wait_observer: ContextVar[Callable[[TransferWait | None], None] | None] = ContextVar("download_wait", default=None)


@contextmanager
def transfer_context(
    cancel: Callable[[], bool], observer: Callable[[TransferWait | None], None],
) -> Iterator[None]:
    c = cancel_check.set(cancel)
    w = wait_observer.set(observer)
    try:
        yield
    finally:
        wait_observer.reset(w)
        cancel_check.reset(c)
