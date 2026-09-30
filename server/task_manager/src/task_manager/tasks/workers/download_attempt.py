from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator


_ATTEMPT_LOCKS: dict[int, threading.Lock] = {}
_ATTEMPT_LOCKS_GUARD = threading.Lock()


@contextmanager
def serialize_download_attempt(media_download_id: int, *, progress=None) -> Iterator[None]:
    """Prevent replacement workers from touching one output path concurrently.

    Cancellation/restart ownership is handled generically by TaskRun and
    TaskOperation. This per-artifact lock only protects the filesystem boundary:
    a replacement worker waits until the cooperatively canceled predecessor has
    released the path before it starts writing.
    """
    with _ATTEMPT_LOCKS_GUARD:
        lock = _ATTEMPT_LOCKS.setdefault(media_download_id, threading.Lock())
    from dailywire_downloader import DownloadCancelled
    waiting = False
    acquired = False
    try:
        while not acquired:
            if progress is not None and callable(progress) and progress():
                raise DownloadCancelled("Canceled while waiting for the previous attempt")
            acquired = lock.acquire(timeout=0.1)
            if not acquired and not waiting and hasattr(progress, "set_wait_state"):
                progress.set_wait_state("previous_attempt", "Waiting for the previous download to stop")
                waiting = True
        if waiting:
            progress.set_wait_state(None)
            waiting = False
        yield
    finally:
        if acquired:
            lock.release()
        if waiting:
            progress.set_wait_state(None)
