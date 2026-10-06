from __future__ import annotations

import hashlib
import logging
import os
import stat
from dataclasses import dataclass
from itertools import count
from pathlib import Path

from .claims import DownloadPathClaimJournal, DownloadPathClaimType
from .helpers import (
    _numbered_candidate,
    _path_exists,
    _path_is_within,
    _unlink_if_identity,
    _write_all,
)

logger = logging.getLogger(__name__)

_RESERVATION_MARKER_PREFIX = ".wireloft-download-reservation-"
_RESERVATION_MARKER_MAGIC = b"WIRELOFT_DOWNLOAD_PATH_RESERVATION_V1\0"
_MAX_MARKER_BYTES = 8192


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


def _clear_empty_placeholder(path: Path, identity: tuple[int, int] | None) -> bool:
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
    if identity is None:
        return True
    if (current.st_dev, current.st_ino) != identity:
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
    path_claims: DownloadPathClaimJournal | None = None
    recovery_record_id: str | None = None

    def release_if_unclaimed(self) -> None:
        """Remove our placeholder if no completed file replaced it, then release its marker."""
        if not _clear_empty_placeholder(self.path, (self.stat_dev, self.stat_ino)):
            return
        marker_removed = _unlink_if_identity(
            self.marker_path,
            stat_dev=self.marker_stat_dev,
            stat_ino=self.marker_stat_ino,
        )
        if (
            self.path_claims is not None
            and self.recovery_record_id is not None
            and (marker_removed or not _path_exists(self.marker_path))
        ):
            self.path_claims.delete_claim(self.recovery_record_id)


def reserve_unique_download_path(
    path: str | Path,
    *,
    path_claims: DownloadPathClaimJournal | None = None,
) -> DownloadPathReservation:
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
        candidate = _numbered_candidate(requested, number)
        recovery_record = (
            path_claims.create_claim(DownloadPathClaimType.DIRECT_RESERVATION, candidate)
            if path_claims is not None
            else None
        )
        if path_claims is not None and recovery_record is None:
            continue
        marker = _marker_path(candidate)

        try:
            marker_fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            if recovery_record is not None:
                path_claims.delete_claim(recovery_record.id)
            continue
        except BaseException:
            if recovery_record is not None:
                path_claims.delete_claim(recovery_record.id)
            raise

        marker_stat = os.fstat(marker_fd)
        destination_fd: int | None = None
        destination_stat: os.stat_result | None = None
        failed = False
        try:
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
                marker_removed = _unlink_if_identity(
                    marker,
                    stat_dev=marker_stat.st_dev,
                    stat_ino=marker_stat.st_ino,
                )
                if (
                    recovery_record is not None
                    and (marker_removed or not _path_exists(marker))
                ):
                    path_claims.delete_claim(recovery_record.id)

        return DownloadPathReservation(
            path=candidate,
            marker_path=marker,
            stat_dev=destination_stat.st_dev,
            stat_ino=destination_stat.st_ino,
            marker_stat_dev=marker_stat.st_dev,
            marker_stat_ino=marker_stat.st_ino,
            path_claims=path_claims,
            recovery_record_id=recovery_record.id if recovery_record is not None else None,
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


def cleanup_abandoned_direct_download_path_reservations(
    download_root: str | Path,
    *,
    path_claims: DownloadPathClaimJournal | None = None,
) -> int:
    """Remove abandoned direct-download claims.

    With a durable claim journal, recovery is targeted and never walks the library.
    Without one, retain the standalone filesystem-only fallback.
    """
    root = Path(os.path.abspath(download_root))
    try:
        if not root.is_dir():
            return 0
    except OSError:
        logger.warning(
            "Could not inspect downloads directory '%s' for abandoned reservations",
            root,
            exc_info=True,
        )
        return 0

    removed = 0

    if path_claims is not None:
        for recovery_record in path_claims.list_claims(
            DownloadPathClaimType.DIRECT_RESERVATION
        ):
            candidate = recovery_record.candidate_path
            if not _path_is_within(candidate, root):
                logger.warning(
                    "Preserving download path claim '%s' because '%s' is outside the configured download root '%s'",
                    recovery_record.id,
                    candidate,
                    root,
                )
                continue

            marker = _marker_path(candidate)
            try:
                marker_stat = marker.lstat()
            except FileNotFoundError:
                if path_claims.delete_claim(recovery_record.id):
                    removed += 1
                continue
            except OSError:
                logger.warning(
                    "Could not inspect download reservation marker '%s'",
                    marker,
                    exc_info=True,
                )
                continue

            if not stat.S_ISREG(marker_stat.st_mode):
                if path_claims.delete_claim(recovery_record.id):
                    removed += 1
                continue

            try:
                with marker.open("rb") as handle:
                    payload = handle.read(_MAX_MARKER_BYTES + 1)
            except FileNotFoundError:
                if path_claims.delete_claim(recovery_record.id):
                    removed += 1
                continue
            except OSError:
                logger.warning(
                    "Could not inspect download reservation marker '%s'",
                    marker,
                    exc_info=True,
                )
                continue

            managed_marker = (
                payload == b""
                or _RESERVATION_MARKER_MAGIC.startswith(payload)
                or payload.startswith(_RESERVATION_MARKER_MAGIC)
            )
            if not managed_marker:
                if path_claims.delete_claim(recovery_record.id):
                    removed += 1
                continue

            decoded = (
                _decode_marker(marker, payload)
                if len(payload) <= _MAX_MARKER_BYTES
                else None
            )
            marker_may_be_released = True
            if decoded is not None:
                decoded_candidate, identity = decoded
                if Path(os.path.abspath(decoded_candidate)) != candidate:
                    logger.warning(
                        "Download reservation marker '%s' does not match its recovery journal path '%s'; preserving the filesystem entry",
                        marker,
                        candidate,
                    )
                    if path_claims.delete_claim(recovery_record.id):
                        removed += 1
                    continue
                marker_may_be_released = _clear_empty_placeholder(candidate, identity)

            if not marker_may_be_released:
                continue

            marker_removed = _unlink_if_identity(
                marker,
                stat_dev=marker_stat.st_dev,
                stat_ino=marker_stat.st_ino,
            )
            if marker_removed or not _path_exists(marker):
                if path_claims.delete_claim(recovery_record.id):
                    removed += 1

        if removed:
            logger.warning(
                "Recovered %s abandoned direct download path claim(s) from a previous WireLoft process",
                removed,
            )
        return removed

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
                logger.warning(
                    "Could not inspect download reservation marker '%s'",
                    marker,
                    exc_info=True,
                )
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
            "Removed %s abandoned download filesystem reservation(s) from a previous WireLoft process",
            removed,
        )
    return removed
