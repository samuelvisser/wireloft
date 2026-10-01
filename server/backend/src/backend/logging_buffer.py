from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone

_MAX_LOG_ENTRIES = 20_000
_lock = threading.Lock()
_entries: deque["ApplicationLogEntry"] = deque(maxlen=_MAX_LOG_ENTRIES)
_next_id = 1


@dataclass(frozen=True)
class ApplicationLogEntry:
    id: int
    timestamp: datetime
    level: str
    logger: str
    message: str
    exception: str | None = None


class _ApplicationLogHandler(logging.Handler):
    """Keep a bounded process-wide copy of emitted log records for the UI."""

    def emit(self, record: logging.LogRecord) -> None:
        # A record can pass through both a non-propagating uvicorn logger and the
        # root logger. Mark it on first capture so it only appears once.
        if getattr(record, "_wireloft_log_buffered", False):
            return
        record._wireloft_log_buffered = True

        global _next_id
        exception = None
        if record.exc_info:
            formatter = self.formatter or logging.Formatter()
            exception = formatter.formatException(record.exc_info)

        entry = ApplicationLogEntry(
            id=0,
            timestamp=datetime.fromtimestamp(record.created, tz=timezone.utc),
            level=record.levelname,
            logger=record.name,
            message=record.getMessage(),
            exception=exception,
        )
        with _lock:
            entry = ApplicationLogEntry(
                id=_next_id,
                timestamp=entry.timestamp,
                level=entry.level,
                logger=entry.logger,
                message=entry.message,
                exception=entry.exception,
            )
            _next_id += 1
            _entries.append(entry)


_handler = _ApplicationLogHandler()
_handler.setLevel(logging.NOTSET)


def install_application_log_handler(log_level: str | None = None) -> None:
    """Capture records from WireLoft and uvicorn at the configured application level."""

    root = logging.getLogger()
    if log_level:
        root.setLevel(getattr(logging, log_level.upper(), logging.INFO))
    if _handler not in root.handlers:
        root.addHandler(_handler)

    # Uvicorn installs non-propagating loggers. They must receive the same
    # capture handler directly; the record marker above prevents duplicates.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        if not logger.propagate and _handler not in logger.handlers:
            logger.addHandler(_handler)


def get_application_logs() -> list[ApplicationLogEntry]:
    with _lock:
        return list(_entries)


def max_application_log_entries() -> int:
    return _MAX_LOG_ENTRIES
