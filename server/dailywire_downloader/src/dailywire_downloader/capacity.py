"""Cancellable resource leases; presentation labels never own capacity."""
from __future__ import annotations

import fcntl
from contextlib import contextmanager
from pathlib import Path
from threading import Condition
from typing import BinaryIO, Callable, Iterator

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


class ProcessSharedCapacityLimiter(CapacityLimiter):
    """Capacity limiter whose slots can be shared by independent processes.

    APScheduler normally executes downloads in one process, but debug reloads and
    overlapping application lifecycles can briefly leave more than one executor
    alive. A plain in-memory counter then enforces the configured limit once per
    process rather than once per WireLoft instance.

    When a lock root is configured, each capacity slot is represented by an
    advisory file lock. Linux releases those locks automatically when a process
    exits, so stale lock files are harmless and cannot strand capacity.
    """

    def __init__(self, limit: int):
        super().__init__(limit)
        self._lock_root: Path | None = None

    def configure(self, limit: int, *, lock_root: str | Path | None = None) -> None:
        if lock_root is not None:
            root = Path(lock_root)
            root.mkdir(parents=True, exist_ok=True)
        else:
            root = None

        with self._condition:
            self._limit = max(1, int(limit))
            if root is not None:
                self._lock_root = root
            self._condition.notify_all()

    def _try_acquire_file_slot(self) -> BinaryIO | None:
        with self._condition:
            root = self._lock_root
            limit = self._limit
        if root is None:
            return None

        for index in range(limit):
            lock_file = (root / f"slot-{index + 1}.lock").open("a+b")
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                lock_file.close()
                continue
            return lock_file
        return None

    @contextmanager
    def acquire(
        self, *, should_cancel: Callable[[], bool], waiting: Callable[[bool], None],
    ) -> Iterator[None]:
        with self._condition:
            use_file_slots = self._lock_root is not None

        if not use_file_slots:
            with super().acquire(should_cancel=should_cancel, waiting=waiting):
                yield
            return

        announced = False
        lock_file = None
        try:
            while lock_file is None:
                if should_cancel():
                    raise DownloadCancelled("Canceled while waiting for capacity")
                lock_file = self._try_acquire_file_slot()
                if lock_file is not None:
                    break
                if not announced:
                    waiting(True)
                    announced = True
                with self._condition:
                    # Releases from this process notify immediately. Releases in
                    # another process are discovered by the short polling timeout.
                    self._condition.wait(timeout=0.1)

            if announced:
                waiting(False)
                announced = False
            yield
        finally:
            if lock_file is not None:
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
                finally:
                    lock_file.close()
                with self._condition:
                    self._condition.notify_all()
            if announced:
                waiting(False)


class DownloadResources:
    def __init__(self, *, media: int = 5, sidecars: int = 2, processing: int = 2):
        self.media = ProcessSharedCapacityLimiter(media)
        self.sidecars = CapacityLimiter(sidecars)
        self.processing = CapacityLimiter(processing)


resources = DownloadResources()
