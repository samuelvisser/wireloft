from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)


def _write_all(fd: int, content: bytes) -> None:
    remaining = memoryview(content)
    while remaining:
        written = os.write(fd, remaining)
        if written <= 0:
            raise OSError("Could not write filesystem marker")
        remaining = remaining[written:]


def _same_file_identity(path: Path, *, stat_dev: int, stat_ino: int) -> os.stat_result | None:
    try:
        current = path.lstat()
    except FileNotFoundError:
        return None
    except OSError:
        logger.warning("Could not inspect filesystem artifact '%s'", path, exc_info=True)
        return None
    if current.st_dev != stat_dev or current.st_ino != stat_ino:
        return None
    return current


def _unlink_if_identity(
    path: Path,
    *,
    stat_dev: int,
    stat_ino: int,
    require_empty: bool = False,
) -> bool:
    current = _same_file_identity(path, stat_dev=stat_dev, stat_ino=stat_ino)
    if current is None or (require_empty and current.st_size != 0):
        return False
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    except OSError:
        logger.warning("Could not remove filesystem artifact '%s'", path, exc_info=True)
        return False
    return True


def _numbered_candidate(requested: Path, number: int) -> Path:
    if number == 0:
        return requested
    return requested.with_name(f"{requested.stem}-{number}{requested.suffix}")


def _path_is_within(path: Path, root: Path) -> bool:
    absolute_path = Path(os.path.abspath(path))
    absolute_root = Path(os.path.abspath(root))
    try:
        absolute_path.relative_to(absolute_root)
    except ValueError:
        return False
    return True


def _path_exists(path: Path) -> bool:
    return os.path.lexists(path)
