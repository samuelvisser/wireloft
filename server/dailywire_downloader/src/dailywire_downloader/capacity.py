"""Cancellable resource leases; presentation labels never own capacity."""
from __future__ import annotations

from contextlib import contextmanager
from threading import Condition
from typing import Callable, Iterator

from .errors import DownloadCancelled


class CapacityLimiter:
    def __init__(self, limit: int):
        self._condition = Condition()
        self._limit = max(1, limit)
        self._active = 0

    def configure(self, limit: int) -> None:
        with self._condition:
            self._limit = max(1, int(limit))
            self._condition.notify_all()

    @contextmanager
    def acquire(
        self, *, should_cancel: Callable[[], bool], waiting: Callable[[bool], None],
    ) -> Iterator[None]:
        announced = False
        acquired = False
        try:
            while True:
                if should_cancel():
                    raise DownloadCancelled("Canceled while waiting for capacity")
                with self._condition:
                    if self._active < self._limit:
                        self._active += 1
                        acquired = True
                        break
                if not announced:
                    waiting(True)
                    announced = True
                with self._condition:
                    self._condition.wait(timeout=0.1)
            if announced:
                waiting(False)
                announced = False
            yield
        finally:
            if acquired:
                with self._condition:
                    self._active -= 1
                    self._condition.notify_all()
            if announced:
                waiting(False)


class DownloadResources:
    def __init__(self, *, media: int = 5, sidecars: int = 2, processing: int = 2):
        self.media = CapacityLimiter(media)
        self.sidecars = CapacityLimiter(sidecars)
        self.processing = CapacityLimiter(processing)


resources = DownloadResources()
