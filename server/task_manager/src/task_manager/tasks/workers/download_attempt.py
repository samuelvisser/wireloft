from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator


_ATTEMPT_LOCKS: dict[int, threading.Lock] = {}
_ATTEMPT_LOCKS_GUARD = threading.Lock()


@contextmanager
def serialize_download_attempt(media_download_id: int) -> Iterator[None]:
    """Prevent replacement workers from touching one output path concurrently.

    Cancellation/restart ownership is handled generically by TaskRun and
    TaskOperation. This per-artifact lock only protects the filesystem boundary:
    a replacement worker waits until the cooperatively canceled predecessor has
    released the path before it starts writing.
    """
    with _ATTEMPT_LOCKS_GUARD:
        lock = _ATTEMPT_LOCKS.setdefault(media_download_id, threading.Lock())
    with lock:
        yield
