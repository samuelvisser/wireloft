from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import socket


class DatabaseInUseError(RuntimeError):
    """Raised when another WireLoft process already owns a SQLite database."""


def _lock_path(database_path: Path) -> Path:
    return Path(f"{database_path}.wireloft.lock")


def _lock_file(handle) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise BlockingIOError from exc
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_file(handle) -> None:
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
        return

    import fcntl

    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _read_owner(handle) -> str:
    try:
        handle.seek(0)
        raw = handle.read().strip()
    except OSError:
        return ""
    if not raw:
        return ""

    try:
        payload = json.loads(raw)
    except (TypeError, ValueError):
        return raw

    parts = []
    if payload.get("pid") is not None:
        parts.append(f"pid={payload['pid']}")
    if payload.get("host"):
        parts.append(f"host={payload['host']}")
    if payload.get("command"):
        parts.append(f"command={payload['command']}")
    if payload.get("started_at"):
        parts.append(f"started_at={payload['started_at']}")
    return ", ".join(parts)


@dataclass
class DatabaseInstanceLock:
    """Kernel-backed exclusive ownership lock for one WireLoft SQLite database.

    The lock file intentionally remains on disk after release. Lock ownership is
    held by the kernel, not by the file's existence. Keeping one stable inode is
    important: unlinking a lock file on release could let one process keep a lock
    on the old inode while another process creates and locks a replacement file.
    """

    database_path: Path
    command: str
    _handle: object | None = None

    @classmethod
    def acquire(cls, database_path: str | Path, *, command: str) -> "DatabaseInstanceLock":
        database = Path(database_path).resolve()
        database.parent.mkdir(parents=True, exist_ok=True)
        lock_path = _lock_path(database)

        # a+ keeps the lock metadata readable without truncating it before we
        # know whether another process owns the kernel lock.
        handle = lock_path.open("a+", encoding="utf-8")
        try:
            _lock_file(handle)
        except BlockingIOError as exc:
            owner = _read_owner(handle)
            handle.close()
            owner_suffix = f" ({owner})" if owner else ""
            raise DatabaseInUseError(
                f"SQLite database '{database}' is already owned by another WireLoft instance{owner_suffix}. "
                "Stop the other backend before starting WireLoft or running a database-changing command."
            ) from exc
        except Exception:
            handle.close()
            raise

        payload = {
            "pid": os.getpid(),
            "host": socket.gethostname(),
            "command": command,
            "started_at": datetime.now(timezone.utc).isoformat(),
        }
        handle.seek(0)
        handle.truncate(0)
        json.dump(payload, handle, separators=(",", ":"))
        handle.write("\n")
        handle.flush()
        try:
            os.fsync(handle.fileno())
        except OSError:
            # Metadata is diagnostic only; the kernel lock is the authority.
            pass

        return cls(database_path=database, command=command, _handle=handle)

    @property
    def lock_path(self) -> Path:
        return _lock_path(self.database_path)

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return
        self._handle = None
        try:
            _unlock_file(handle)
        finally:
            handle.close()

    def __enter__(self) -> "DatabaseInstanceLock":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.release()
