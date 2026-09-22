from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import os
import shutil
import sqlite3
import subprocess
import tempfile


class DatabaseRecoveryError(RuntimeError):
    """Raised when a corrupt SQLite database cannot be safely salvaged."""


@dataclass(frozen=True)
class DatabaseRecoveryResult:
    source: Path
    recovered: Path
    replaced_source: bool
    backup_directory: Path | None = None


def sqlite_integrity_check(path: str | Path) -> tuple[str, ...]:
    """Run SQLite's full integrity check without changing journal mode."""
    database = Path(path).resolve()
    uri = f"{database.as_uri()}?mode=ro"
    try:
        connection = sqlite3.connect(uri, uri=True, timeout=30)
    except sqlite3.Error as exc:
        raise DatabaseRecoveryError(
            f"Could not open SQLite database '{database}' read-only: {exc}"
        ) from exc

    try:
        return tuple(
            str(row[0])
            for row in connection.execute("PRAGMA integrity_check").fetchall()
        )
    except sqlite3.Error as exc:
        raise DatabaseRecoveryError(
            f"SQLite integrity_check failed for '{database}': {exc}"
        ) from exc
    finally:
        connection.close()


def _default_recovered_path(source: Path, timestamp: str) -> Path:
    suffix = source.suffix or ".db"
    stem = source.name[:-len(source.suffix)] if source.suffix else source.name
    return source.with_name(f"{stem}.recovered-{timestamp}{suffix}")


def _run_recover(sqlite_cli: str, source: Path, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise DatabaseRecoveryError(f"Recovery output already exists: '{output}'")

    fd, sql_path_text = tempfile.mkstemp(
        prefix="wireloft-recovery-",
        suffix=".sql",
        dir=str(output.parent),
    )
    os.close(fd)
    sql_path = Path(sql_path_text)
    try:
        with sql_path.open("wb") as recovered_sql:
            recover = subprocess.run(
                [sqlite_cli, str(source), ".recover --ignore-freelist"],
                stdout=recovered_sql,
                stderr=subprocess.PIPE,
                check=False,
            )
        if recover.returncode != 0:
            stderr = recover.stderr.decode("utf-8", errors="replace").strip()
            raise DatabaseRecoveryError(
                f"sqlite3 .recover failed for '{source}'"
                + (f": {stderr}" if stderr else "")
            )

        with sql_path.open("rb") as recovered_sql:
            restore = subprocess.run(
                [sqlite_cli, str(output)],
                stdin=recovered_sql,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        if restore.returncode != 0:
            stderr = restore.stderr.decode("utf-8", errors="replace").strip()
            output.unlink(missing_ok=True)
            raise DatabaseRecoveryError(
                f"Could not rebuild recovered SQLite database '{output}'"
                + (f": {stderr}" if stderr else "")
            )
    finally:
        sql_path.unlink(missing_ok=True)


def _database_files(source: Path) -> tuple[Path, ...]:
    return (
        source,
        Path(f"{source}-wal"),
        Path(f"{source}-shm"),
        Path(f"{source}-journal"),
    )


def _backup_corrupt_database(source: Path, timestamp: str) -> Path:
    backup_directory = source.with_name(f"{source.name}.corrupt-{timestamp}")
    backup_directory.mkdir(parents=False, exist_ok=False)

    for candidate in _database_files(source):
        if candidate.exists():
            shutil.copy2(candidate, backup_directory / candidate.name)
    return backup_directory


def recover_sqlite_database(
    path: str | Path,
    *,
    output: str | Path | None = None,
    replace: bool = False,
) -> DatabaseRecoveryResult:
    """Salvage a corrupt SQLite database using the official CLI ``.recover`` path.

    Recovery never edits the corrupt file while extracting data. By default a
    separate ``*.recovered-<timestamp>.db`` is produced. With ``replace=True`` a
    timestamped backup of the original DB and its journal sidecars is created
    first; only a recovered database that passes ``integrity_check`` is installed.
    """
    source = Path(path).resolve()
    if not source.is_file():
        raise DatabaseRecoveryError(f"Database file does not exist: '{source}'")

    sqlite_cli = shutil.which("sqlite3")
    if sqlite_cli is None:
        raise DatabaseRecoveryError(
            "SQLite recovery requires the 'sqlite3' command-line tool with .recover support"
        )

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    recovered = (
        Path(output).resolve()
        if output is not None
        else _default_recovered_path(source, timestamp)
    )
    if recovered == source:
        raise DatabaseRecoveryError("Recovery output must differ from the source database")

    _run_recover(sqlite_cli, source, recovered)
    integrity = sqlite_integrity_check(recovered)
    if integrity != ("ok",):
        details = "; ".join(integrity[:10]) or "integrity_check returned no result"
        raise DatabaseRecoveryError(
            f"Recovered database '{recovered}' still fails integrity_check: {details}"
        )

    backup_directory = None
    if replace:
        backup_directory = _backup_corrupt_database(source, timestamp)
        try:
            os.replace(recovered, source)
        except OSError as exc:
            raise DatabaseRecoveryError(
                f"Recovered database is valid, but could not replace '{source}'. "
                f"The original remains in place and its backup is at '{backup_directory}': {exc}"
            ) from exc

        # A WAL/SHM/journal from the corrupt database must never be applied to the
        # newly recovered main database file.
        for sidecar in _database_files(source)[1:]:
            sidecar.unlink(missing_ok=True)
        recovered = source

    return DatabaseRecoveryResult(
        source=source,
        recovered=recovered,
        replaced_source=replace,
        backup_directory=backup_directory,
    )
