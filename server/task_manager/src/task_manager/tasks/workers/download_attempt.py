from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from backend.db.core import get_session
from backend.db.models.media_download import MediaDownloadBase
from dailywire_downloader import DownloadCancelled


_ATTEMPT_LOCKS: dict[int, threading.Lock] = {}
_ATTEMPT_LOCKS_GUARD = threading.Lock()


@contextmanager
def serialize_download_attempt(media_download_id: int) -> Iterator[None]:
    """Prevent old and replacement workers from touching one output together."""
    with _ATTEMPT_LOCKS_GUARD:
        lock = _ATTEMPT_LOCKS.setdefault(media_download_id, threading.Lock())
    with lock:
        yield


class DownloadAttemptGuard:
    """Cooperatively cancels a worker when its persisted generation is stale."""

    def __init__(
            self,
            media_download_id: int,
            attempt_generation: int,
            *,
            check_interval_seconds: float = 0.25,
    ) -> None:
        self._media_download_id = media_download_id
        self._attempt_generation = attempt_generation
        self._check_interval_seconds = check_interval_seconds
        self._last_check = 0.0
        self._cancelled = False

    def __call__(self) -> bool:
        if self._cancelled:
            return True

        now = time.monotonic()
        if now - self._last_check < self._check_interval_seconds:
            return False
        self._last_check = now

        session = get_session()
        try:
            current = session.execute(
                select(MediaDownloadBase.attempt_generation)
                .where(MediaDownloadBase.id == self._media_download_id)
            ).scalar_one_or_none()
            self._cancelled = current is None or current != self._attempt_generation
        except Exception:
            # A transient database lock must not turn into a false cancellation.
            session.rollback()
            return False
        finally:
            session.close()
        return self._cancelled

    def ensure_current(self) -> None:
        # Force a fresh read even if a progress callback just checked.
        self._last_check = 0.0
        if self():
            raise DownloadCancelled("Download attempt was replaced by a retry")

    def update_current(self, session: Session, **values) -> None:
        """Apply row state only if this is still the current attempt."""
        result = session.execute(
            update(MediaDownloadBase)
            .where(
                MediaDownloadBase.id == self._media_download_id,
                MediaDownloadBase.attempt_generation == self._attempt_generation,
            )
            .values(**values)
        )
        if not result.rowcount:
            self._cancelled = True
            raise DownloadCancelled("Download attempt was replaced by a retry")
