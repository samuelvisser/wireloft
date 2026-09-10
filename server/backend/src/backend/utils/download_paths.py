from __future__ import annotations

import hashlib
import logging
import os
import stat
from dataclasses import dataclass
from itertools import count
from pathlib import Path

logger = logging.getLogger(__name__)

_RESERVATION_MARKER_PREFIX = ".wireloft-download-reservation-"
_RESERVATION_MARKER_MAGIC = b"WIRELOFT_DOWNLOAD_PATH_RESERVATION_V1\0"
_MAX_MARKER_BYTES = 8192


def _write_all(fd: int, content: bytes) -> None:
    remaining = memoryview(content)
    while remaining:
        written = os.write(fd, remaining)
        if written <= 0:
            raise OSError("Could not write download path reservation marker")
        remaining = remaining[written:]


def _marker_path(candidate: Path) -> Path:
    digest = hashlib.sha256(os.fsencode(candidate.name)).hexdigest()
    return candidate.parent / f"{_RESERVATION_MARKER_PREFIX}{digest}"


def _marker_payload(candidate: Path) -> bytes:
    return _RESERVATION_MARKER_MAGIC + os.fsencode(candidate.name) + b"\0"


def _is_reservation_marker_name(filename: str) -> bool:
    if not filename.startswith(_RESERVATION_MARKER_PREFIX):
        return False
    digest = filename[len(_RESERVATION_MARKER_PREFIX):]
    return len(digest) == 64 and all(char in "0123456789abcdef" for char in digest)


def _same_file_identity(path: Path, *, stat_dev: int, stat_ino: int) -> os.stat_result | None:
    try:
        current = path.lstat()
    except FileNotFoundError:
        return None
    except OSError:
        logger.warning("Could not inspect download path reservation '%s'", path, exc_info=True)
        return None
    if current.st_dev != stat_dev or current.st_ino != stat_ino:
        return None
    return current


def _unlink_if_identity(path: Path, *, stat_dev: int, stat_ino: int, require_empty: bool = False) -> bool:
    current = _same_file_identity(path, stat_dev=stat_dev, stat_ino=stat_ino)
    if current is None or (require_empty and current.st_size != 0):
        return False
    try:
        path.unlink()
    except FileNotFoundError:
        return False
    except OSError:
        logger.warning("Could not remove download path reservation '%s'", path, exc_info=True)
        return False
    return True


def _clear_empty_placeholder(
    path: Path,
    identity: tuple[int, int] | None,
) -> bool:
    """Clear one abandoned placeholder and report whether its marker may be released."""
    try:
        current = path.lstat()
    except FileNotFoundError:
        return True
    except OSError:
        logger.warning("Could not inspect download path reservation '%s'", path, exc_info=True)
        return False

    if not stat.S_ISREG(current.st_mode) or current.st_size != 0:
        return True
    if identity is not None and (current.st_dev, current.st_ino) != identity:
        return True

    try:
        path.unlink()
    except FileNotFoundError:
        return True
    except OSError:
        logger.warning("Could not remove download path reservation '%s'", path, exc_info=True)
        return False
    return True


@dataclass(frozen=True)
class DownloadPathReservation:
    """One filesystem-level claim on a concrete download destination."""

    path: Path
    marker_path: Path
    stat_dev: int
    stat_ino: int
    marker_stat_dev: int
    marker_stat_ino: int

    def release_if_unclaimed(self) -> None:
        """Remove our placeholder if no completed file replaced it, then release its marker."""
        if not _clear_empty_placeholder(self.path, (self.stat_dev, self.stat_ino)):
            return
        _unlink_if_identity(
            self.marker_path,
            stat_dev=self.marker_stat_dev,
            stat_ino=self.marker_stat_ino,
        )


def reserve_unique_download_path(path: str | Path) -> DownloadPathReservation:
    """Atomically claim the first unused exact filename on the filesystem.

    The supplied path must already contain the concrete media extension. Existing
    entries with other extensions do not collide. If the requested filename is
    occupied, ``-1``, ``-2``, and so on are inserted before the extension.

    A hidden WireLoft marker is claimed first and the empty destination itself is
    then created with ``O_EXCL``. The marker makes an abandoned placeholder
    discoverable after an unclean shutdown without treating unrelated zero-byte
    files as WireLoft artifacts. The downloader later atomically replaces the
    empty destination with its completed temporary file.
    """
    requested = Path(path)
    requested.parent.mkdir(parents=True, exist_ok=True)

    for number in count(0):
        candidate = (
            requested
            if number == 0
            else requested.with_name(f"{requested.stem}-{number}{requested.suffix}")
        )
        marker = _marker_path(candidate)

        try:
            marker_fd = os.open(
                marker,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError:
            continue

        marker_stat = os.fstat(marker_fd)
        destination_fd: int | None = None
        destination_stat: os.stat_result | None = None
        failed = False
        try:
            # Persist the candidate name before creating the final placeholder.
            # If the process dies before this write completes, no destination has
            # been created yet and startup only needs to remove the partial marker.
            _write_all(marker_fd, _marker_payload(candidate))

            try:
                destination_fd = os.open(
                    candidate,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                    0o666,
                )
            except FileExistsError:
                continue

            destination_stat = os.fstat(destination_fd)
            _write_all(
                marker_fd,
                f"{destination_stat.st_dev}:{destination_stat.st_ino}".encode("ascii"),
            )
        except BaseException:
            failed = True
            raise
        finally:
            if destination_fd is not None:
                os.close(destination_fd)
            os.close(marker_fd)
            if failed and destination_stat is not None:
                _unlink_if_identity(
                    candidate,
                    stat_dev=destination_stat.st_dev,
                    stat_ino=destination_stat.st_ino,
                    require_empty=True,
                )
            if failed or destination_stat is None:
                _unlink_if_identity(
                    marker,
                    stat_dev=marker_stat.st_dev,
                    stat_ino=marker_stat.st_ino,
                )

        return DownloadPathReservation(
            path=candidate,
            marker_path=marker,
            stat_dev=destination_stat.st_dev,
            stat_ino=destination_stat.st_ino,
            marker_stat_dev=marker_stat.st_dev,
            marker_stat_ino=marker_stat.st_ino,
        )

    raise RuntimeError("Could not allocate a unique download path")


def _decode_marker(marker: Path, payload: bytes) -> tuple[Path, tuple[int, int] | None] | None:
    if not payload.startswith(_RESERVATION_MARKER_MAGIC):
        return None

    encoded = payload[len(_RESERVATION_MARKER_MAGIC):]
    if b"\0" not in encoded:
        return None
    encoded_name, encoded_identity = encoded.split(b"\0", 1)
    if not encoded_name:
        return None

    candidate_name = os.fsdecode(encoded_name)
    if candidate_name in {"", ".", ".."} or Path(candidate_name).name != candidate_name:
        return None

    candidate = marker.parent / candidate_name
    if _marker_path(candidate).name != marker.name:
        return None

    identity: tuple[int, int] | None = None
    if encoded_identity:
        try:
            stat_dev_text, stat_ino_text = encoded_identity.decode("ascii").split(":", 1)
            identity = (int(stat_dev_text), int(stat_ino_text))
        except (UnicodeDecodeError, ValueError):
            identity = None
    return candidate, identity


def cleanup_abandoned_download_path_reservations(download_root: str | Path) -> int:
    """Remove filesystem reservations left behind by a previous WireLoft process.

    Only WireLoft's hidden reservation markers are considered. Arbitrary empty
    files in the downloads tree are never treated as abandoned placeholders.
    Completed files are preserved even when a crash happened after the downloader
    replaced the placeholder but before it could remove the marker.
    """
    root = Path(download_root)
    try:
        if not root.is_dir():
            return 0
    except OSError:
        logger.warning("Could not inspect downloads directory '%s' for abandoned reservations", root, exc_info=True)
        return 0

    removed = 0

    def walk_error(error: OSError) -> None:
        logger.warning("Could not scan downloads directory for abandoned reservations: %s", error)

    for directory, _subdirs, filenames in os.walk(root, onerror=walk_error, followlinks=False):
        parent = Path(directory)
        for filename in filenames:
            if not _is_reservation_marker_name(filename):
                continue

            marker = parent / filename
            try:
                marker_stat = marker.lstat()
                if not stat.S_ISREG(marker_stat.st_mode):
                    continue
                with marker.open("rb") as handle:
                    payload = handle.read(_MAX_MARKER_BYTES + 1)
            except FileNotFoundError:
                continue
            except OSError:
                logger.warning("Could not inspect download reservation marker '%s'", marker, exc_info=True)
                continue

            managed_marker = (
                payload == b""
                or _RESERVATION_MARKER_MAGIC.startswith(payload)
                or payload.startswith(_RESERVATION_MARKER_MAGIC)
            )
            if not managed_marker:
                continue

            decoded = _decode_marker(marker, payload) if len(payload) <= _MAX_MARKER_BYTES else None
            marker_may_be_released = True
            if decoded is not None:
                candidate, identity = decoded
                marker_may_be_released = _clear_empty_placeholder(candidate, identity)

            if marker_may_be_released and _unlink_if_identity(
                marker,
                stat_dev=marker_stat.st_dev,
                stat_ino=marker_stat.st_ino,
            ):
                removed += 1

    if removed:
        logger.warning(
            "Removed %s abandoned download path reservation(s) from a previous WireLoft process",
            removed,
        )
    return removed
