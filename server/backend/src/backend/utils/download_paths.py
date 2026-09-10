from __future__ import annotations

import ctypes
import errno
import hashlib
import json
import logging
import os
import shutil
import stat
import sys
import tempfile
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from itertools import count
from pathlib import Path

from backend.utils.artifact_identity import ArtifactIdentity, inspect_artifact

logger = logging.getLogger(__name__)

_RESERVATION_MARKER_PREFIX = ".wireloft-download-reservation-"
_RESERVATION_MARKER_MAGIC = b"WIRELOFT_DOWNLOAD_PATH_RESERVATION_V1\0"
_PUBLICATION_LOCK_PREFIX = ".wireloft-publish-lock-"
_PUBLICATION_LOCK_MAGIC = b"WIRELOFT_PUBLICATION_LOCK_V1\0"
_PORTABLE_PUBLICATION_PREFIX = ".wireloft-publish-"
_PORTABLE_PUBLICATION_SUFFIX = ".part"
_MAX_MARKER_BYTES = 8192
_STAGING_DIRECTORY_NAME = ".wireloft-staging"
_STAGING_WORKSPACE_PREFIX = "attempt-"
_STAGING_PUBLICATION_MARKER = ".wireloft-publication"
_STAGING_PUBLICATION_MAGIC_V1 = b"WIRELOFT_STAGED_DOWNLOAD_PUBLICATION_V1\0"
_STAGING_PUBLICATION_MAGIC_V2 = b"WIRELOFT_STAGED_DOWNLOAD_PUBLICATION_V2\0"
_AT_FDCWD = -100
_RENAME_NOREPLACE = 1


class TemporaryDownloadFilesystemError(RuntimeError):
    """Raised when a completed temporary download cannot be published safely."""


def _write_all(fd: int, content: bytes) -> None:
    remaining = memoryview(content)
    while remaining:
        written = os.write(fd, remaining)
        if written <= 0:
            raise OSError("Could not write filesystem marker")
        remaining = remaining[written:]


def _marker_path(candidate: Path) -> Path:
    digest = hashlib.sha256(os.fsencode(candidate.name)).hexdigest()
    return candidate.parent / f"{_RESERVATION_MARKER_PREFIX}{digest}"


def _marker_payload(candidate: Path) -> bytes:
    return _RESERVATION_MARKER_MAGIC + os.fsencode(candidate.name) + b"\0"


def _publication_lock_path(candidate: Path) -> Path:
    digest = hashlib.sha256(os.fsencode(candidate.name)).hexdigest()
    return candidate.parent / f"{_PUBLICATION_LOCK_PREFIX}{digest}"


def _publication_lock_payload(candidate: Path) -> bytes:
    return _PUBLICATION_LOCK_MAGIC + os.fsencode(candidate.name) + b"\0"


def _is_reservation_marker_name(filename: str) -> bool:
    if not filename.startswith(_RESERVATION_MARKER_PREFIX):
        return False
    digest = filename[len(_RESERVATION_MARKER_PREFIX):]
    return len(digest) == 64 and all(char in "0123456789abcdef" for char in digest)


def _is_publication_lock_name(filename: str) -> bool:
    if not filename.startswith(_PUBLICATION_LOCK_PREFIX):
        return False
    digest = filename[len(_PUBLICATION_LOCK_PREFIX):]
    return len(digest) == 64 and all(char in "0123456789abcdef" for char in digest)


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


def _unlink_if_identity(path: Path, *, stat_dev: int, stat_ino: int, require_empty: bool = False) -> bool:
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


@dataclass(frozen=True)
class _PublicationLock:
    path: Path
    stat_dev: int
    stat_ino: int

    def release(self) -> None:
        _unlink_if_identity(self.path, stat_dev=self.stat_dev, stat_ino=self.stat_ino)


@dataclass(frozen=True)
class TemporaryDownloadWorkspace:
    """Private staging workspace for one download attempt."""

    path: Path
    workspace: Path

    def cleanup(self) -> None:
        try:
            shutil.rmtree(self.workspace)
        except FileNotFoundError:
            pass
        except OSError:
            logger.warning(
                "Could not remove temporary download workspace '%s'",
                self.workspace,
                exc_info=True,
            )


@dataclass(frozen=True)
class _PortablePublicationRecord:
    phase: str
    portable_path: Path
    candidate: Path | None = None
    size_bytes: int | None = None
    fingerprint: str | None = None


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
        candidate = _numbered_candidate(requested, number)
        marker = _marker_path(candidate)

        try:
            marker_fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            continue

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


def create_temporary_download_workspace(
    temporary_root: str | Path,
    requested_destination: str | Path,
) -> TemporaryDownloadWorkspace:
    """Create a private staging path for one download attempt.

    The configured temporary folder may be on any filesystem, including local
    storage while the final library is on a network mount. Cross-filesystem work
    is handled only after the download is complete.
    """
    requested = Path(requested_destination)
    staging_root = Path(temporary_root) / _STAGING_DIRECTORY_NAME
    staging_root.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix=_STAGING_WORKSPACE_PREFIX, dir=staging_root))
    return TemporaryDownloadWorkspace(
        path=workspace / f"download{requested.suffix}",
        workspace=workspace,
    )


def _atomic_write_workspace_marker(workspace: Path, payload: bytes) -> None:
    if len(payload) > _MAX_MARKER_BYTES:
        raise TemporaryDownloadFilesystemError(
            "Temporary download publication record is too large to store safely."
        )

    marker = workspace / _STAGING_PUBLICATION_MARKER
    temporary_marker = workspace / f"{_STAGING_PUBLICATION_MARKER}.{uuid.uuid4().hex}.tmp"
    fd = os.open(temporary_marker, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        _write_all(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    try:
        os.replace(temporary_marker, marker)
    finally:
        try:
            temporary_marker.unlink()
        except FileNotFoundError:
            pass


def _write_portable_publication_record(
    staged: Path,
    *,
    phase: str,
    portable_path: Path,
    candidate: Path | None = None,
    identity: ArtifactIdentity | None = None,
) -> None:
    record: dict[str, object] = {
        "phase": phase,
        "portable_path": os.path.abspath(portable_path),
    }
    if candidate is not None:
        record["candidate"] = os.path.abspath(candidate)
    if identity is not None:
        record["size_bytes"] = identity.size_bytes
        record["fingerprint"] = identity.fingerprint
    payload = _STAGING_PUBLICATION_MAGIC_V2 + json.dumps(
        record,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    _atomic_write_workspace_marker(staged.parent, payload)


def _decode_portable_publication_record(payload: bytes) -> _PortablePublicationRecord | None:
    if not payload.startswith(_STAGING_PUBLICATION_MAGIC_V2):
        return None
    try:
        raw = json.loads(payload[len(_STAGING_PUBLICATION_MAGIC_V2):].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None

    phase = raw.get("phase")
    portable_text = raw.get("portable_path")
    if phase not in {"copy", "publish"} or not isinstance(portable_text, str):
        return None
    portable = Path(portable_text)
    if not portable.is_absolute():
        return None

    candidate: Path | None = None
    size_bytes: int | None = None
    fingerprint: str | None = None
    if phase == "publish":
        candidate_text = raw.get("candidate")
        size_bytes = raw.get("size_bytes")
        fingerprint = raw.get("fingerprint")
        if (
            not isinstance(candidate_text, str)
            or not isinstance(size_bytes, int)
            or size_bytes < 0
            or not isinstance(fingerprint, str)
            or len(fingerprint) != 64
        ):
            return None
        candidate = Path(candidate_text)
        if not candidate.is_absolute():
            return None

    return _PortablePublicationRecord(
        phase=phase,
        portable_path=portable,
        candidate=candidate,
        size_bytes=size_bytes,
        fingerprint=fingerprint,
    )


def _decode_legacy_staging_publication_marker(
    workspace: Path,
    payload: bytes,
) -> tuple[Path, Path, tuple[int, int]] | None:
    if not payload.startswith(_STAGING_PUBLICATION_MAGIC_V1):
        return None

    encoded = payload[len(_STAGING_PUBLICATION_MAGIC_V1):]
    parts = encoded.split(b"\0")
    if len(parts) != 3 or not all(parts):
        return None

    staged_name = os.fsdecode(parts[0])
    if Path(staged_name).name != staged_name or staged_name in {"", ".", ".."}:
        return None

    candidate = Path(os.fsdecode(parts[1]))
    if not candidate.is_absolute():
        return None

    try:
        stat_dev_text, stat_ino_text = parts[2].decode("ascii").split(":", 1)
        identity = (int(stat_dev_text), int(stat_ino_text))
    except (UnicodeDecodeError, ValueError):
        return None

    return workspace / staged_name, candidate, identity


def _claim_publication_lock(candidate: Path) -> _PublicationLock | None:
    lock_path = _publication_lock_path(candidate)
    try:
        fd = os.open(lock_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        return None

    lock_stat = os.fstat(fd)
    failed = False
    try:
        _write_all(fd, _publication_lock_payload(candidate))
        os.fsync(fd)
    except BaseException:
        failed = True
        raise
    finally:
        os.close(fd)
        if failed:
            _unlink_if_identity(
                lock_path,
                stat_dev=lock_stat.st_dev,
                stat_ino=lock_stat.st_ino,
            )

    return _PublicationLock(lock_path, lock_stat.st_dev, lock_stat.st_ino)


def _portable_publication_path(parent: Path) -> Path:
    return parent / f"{_PORTABLE_PUBLICATION_PREFIX}{uuid.uuid4().hex}{_PORTABLE_PUBLICATION_SUFFIX}"


def _copy_completed_file(source: Path, destination: Path) -> None:
    try:
        os.replace(source, destination)
        return
    except OSError as exc:
        if exc.errno != errno.EXDEV:
            raise TemporaryDownloadFilesystemError(
                f"Could not move completed temporary download into destination staging: {exc}"
            ) from exc

    try:
        with source.open("rb") as source_file, destination.open("xb") as destination_file:
            shutil.copyfileobj(source_file, destination_file, length=1024 * 1024)
            destination_file.flush()
            os.fsync(destination_file.fileno())
    except BaseException:
        try:
            destination.unlink()
        except FileNotFoundError:
            pass
        raise


def _linux_rename_noreplace(source: Path, destination: Path) -> bool:
    """Use Linux RENAME_NOREPLACE when the kernel/filesystem supports it."""
    if not sys.platform.startswith("linux"):
        return False
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        renameat2 = libc.renameat2
    except (AttributeError, OSError):
        return False

    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    result = renameat2(
        _AT_FDCWD,
        os.fsencode(source),
        _AT_FDCWD,
        os.fsencode(destination),
        _RENAME_NOREPLACE,
    )
    if result == 0:
        return True

    error = ctypes.get_errno()
    if error == errno.EEXIST:
        raise FileExistsError(error, os.strerror(error), destination)
    unsupported_errors = {errno.ENOSYS, errno.EINVAL}
    for name in ("EOPNOTSUPP", "ENOTSUP"):
        value = getattr(errno, name, None)
        if value is not None:
            unsupported_errors.add(value)
    if error in unsupported_errors:
        return False
    raise OSError(error, os.strerror(error), destination)


def _publish_complete_file(source: Path, destination: Path) -> None:
    """Rename a complete destination-side staging file into its final name."""
    if os.name == "nt":
        os.rename(source, destination)
        return
    if _linux_rename_noreplace(source, destination):
        return

    # POSIX rename normally replaces an existing destination. The hidden
    # filesystem lock serializes all WireLoft publishers, and we re-check the
    # final path immediately before this fallback. Generic POSIX has no portable
    # no-replace rename primitive, so an unrelated external writer racing in this
    # tiny window cannot be made atomic on every filesystem.
    if _path_exists(destination):
        raise FileExistsError(destination)
    os.replace(source, destination)


def publish_temporary_download(
    staged_path: str | Path,
    requested_destination: str | Path,
) -> Path:
    """Publish a completed staged file under the first unused exact filename.

    The primary staging directory may live on any filesystem. WireLoft first
    moves the completed file into a hidden ``.part`` path beside its destination;
    if the filesystems differ it copies the already-complete file there instead.
    The final media filename is then created only by a same-filesystem rename.

    A hidden per-candidate lock keeps concurrent WireLoft workers collision-safe.
    Linux ``RENAME_NOREPLACE`` and Windows' non-overwriting rename semantics are
    used when available; other filesystems use the lock plus an immediate final
    existence check before the portable rename fallback.
    """
    staged = Path(staged_path)
    requested = Path(requested_destination)
    requested.parent.mkdir(parents=True, exist_ok=True)

    try:
        staged_identity = inspect_artifact(staged)
    except FileNotFoundError as exc:
        raise TemporaryDownloadFilesystemError(
            f"Completed temporary download no longer exists: {staged}"
        ) from exc
    except (OSError, ValueError) as exc:
        raise TemporaryDownloadFilesystemError(
            f"Could not inspect completed temporary download '{staged}': {exc}"
        ) from exc

    portable = _portable_publication_path(requested.parent)
    _write_portable_publication_record(
        staged,
        phase="copy",
        portable_path=portable,
    )

    try:
        _copy_completed_file(staged, portable)
        portable_identity = inspect_artifact(portable)
        if (
            portable_identity.size_bytes != staged_identity.size_bytes
            or portable_identity.fingerprint != staged_identity.fingerprint
        ):
            raise TemporaryDownloadFilesystemError(
                "Completed temporary download changed while being copied to its destination filesystem."
            )

        for number in count(0):
            candidate = _numbered_candidate(requested, number)
            lock = _claim_publication_lock(candidate)
            if lock is None:
                continue
            try:
                if _path_exists(candidate):
                    continue

                _write_portable_publication_record(
                    staged,
                    phase="publish",
                    portable_path=portable,
                    candidate=candidate,
                    identity=portable_identity,
                )
                try:
                    _publish_complete_file(portable, candidate)
                except FileExistsError:
                    continue
                return candidate
            finally:
                lock.release()
    except BaseException:
        try:
            portable.unlink()
        except FileNotFoundError:
            pass
        raise

    raise RuntimeError("Could not publish temporary download to a unique path")


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
    """Remove WireLoft filesystem claims left behind by a previous process."""
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
            marker = parent / filename
            if _is_publication_lock_name(filename):
                try:
                    marker_stat = marker.lstat()
                    if not stat.S_ISREG(marker_stat.st_mode):
                        continue
                    with marker.open("rb") as handle:
                        payload = handle.read(_MAX_MARKER_BYTES + 1)
                except FileNotFoundError:
                    continue
                except OSError:
                    logger.warning("Could not inspect publication lock '%s'", marker, exc_info=True)
                    continue

                managed = (
                    payload == b""
                    or _PUBLICATION_LOCK_MAGIC.startswith(payload)
                    or payload.startswith(_PUBLICATION_LOCK_MAGIC)
                )
                if managed and _unlink_if_identity(
                    marker,
                    stat_dev=marker_stat.st_dev,
                    stat_ino=marker_stat.st_ino,
                ):
                    removed += 1
                continue

            if not _is_reservation_marker_name(filename):
                continue

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
            "Removed %s abandoned download filesystem reservation(s) from a previous WireLoft process",
            removed,
        )
    return removed


def _remove_workspace(workspace: Path) -> bool:
    try:
        if workspace.is_symlink() or not workspace.is_dir():
            workspace.unlink(missing_ok=True)
        else:
            shutil.rmtree(workspace)
    except FileNotFoundError:
        return True
    except OSError:
        logger.warning(
            "Could not remove abandoned temporary download workspace '%s'",
            workspace,
            exc_info=True,
        )
        return False
    return True


def _remove_portable_publication_file(path: Path, download_root: Path) -> bool:
    if not _path_is_within(path, download_root):
        return False
    if not (
        path.name.startswith(_PORTABLE_PUBLICATION_PREFIX)
        and path.name.endswith(_PORTABLE_PUBLICATION_SUFFIX)
    ):
        return False
    try:
        path.unlink()
    except FileNotFoundError:
        return True
    except OSError:
        logger.warning("Could not remove abandoned publication file '%s'", path, exc_info=True)
        return False
    return True


def _artifact_matches_record(identity: ArtifactIdentity, record: _PortablePublicationRecord) -> bool:
    return (
        identity.size_bytes == record.size_bytes
        and identity.fingerprint == record.fingerprint
    )


def cleanup_abandoned_temporary_downloads(
    temporary_root: str | Path,
    download_root: str | Path,
    *,
    is_published_artifact: Callable[[Path, ArtifactIdentity], bool],
) -> int:
    """Reconcile temporary publication workspaces left by an unclean shutdown."""
    staging_root = Path(temporary_root) / _STAGING_DIRECTORY_NAME
    download_root_path = Path(download_root)
    try:
        entries = list(staging_root.iterdir())
    except FileNotFoundError:
        return 0
    except OSError:
        logger.warning(
            "Could not inspect temporary download directory '%s' for abandoned workspaces",
            staging_root,
            exc_info=True,
        )
        return 0

    removed = 0
    for workspace in entries:
        if not workspace.name.startswith(_STAGING_WORKSPACE_PREFIX):
            continue
        if workspace.is_symlink() or not workspace.is_dir():
            if _remove_workspace(workspace):
                removed += 1
            continue

        marker = workspace / _STAGING_PUBLICATION_MARKER
        try:
            payload = marker.read_bytes()
        except FileNotFoundError:
            payload = b""
        except OSError:
            logger.warning(
                "Could not inspect temporary download publication marker '%s'",
                marker,
                exc_info=True,
            )
            continue

        if not payload:
            if _remove_workspace(workspace):
                removed += 1
            continue
        if len(payload) > _MAX_MARKER_BYTES:
            logger.warning(
                "Temporary download publication marker '%s' is too large; preserving workspace for safety",
                marker,
            )
            continue

        portable_record = _decode_portable_publication_record(payload)
        if portable_record is not None:
            portable = portable_record.portable_path
            if not _path_is_within(portable, download_root_path):
                logger.warning(
                    "Temporary publication record '%s' points outside the download root; preserving workspace for safety",
                    marker,
                )
                continue

            portable_still_exists = _path_exists(portable)
            if portable_record.phase == "publish" and not portable_still_exists:
                # A successful final rename consumes the hidden destination-side
                # publication file. If it still exists, the attempted final name
                # was never ours (for example because RENAME_NOREPLACE collided),
                # so recovery must never inspect or remove that candidate.
                candidate = portable_record.candidate
                if candidate is None or not _path_is_within(candidate, download_root_path):
                    logger.warning(
                        "Temporary publication record '%s' has an unsafe final path; preserving workspace for safety",
                        marker,
                    )
                    continue

                try:
                    candidate_identity = inspect_artifact(candidate)
                except FileNotFoundError:
                    candidate_identity = None
                except (OSError, ValueError):
                    logger.warning(
                        "Could not inspect published temporary file '%s'; preserving workspace for safety",
                        candidate,
                        exc_info=True,
                    )
                    continue

                if candidate_identity is not None:
                    if not _artifact_matches_record(candidate_identity, portable_record):
                        logger.warning(
                            "Published temporary path '%s' no longer matches WireLoft's publication record; preserving it",
                            candidate,
                        )
                        continue
                    try:
                        committed = is_published_artifact(candidate, candidate_identity)
                    except Exception:
                        logger.warning(
                            "Could not verify whether staged download '%s' was committed; preserving workspace for safety",
                            candidate,
                            exc_info=True,
                        )
                        continue

                    if not committed:
                        try:
                            current_identity = inspect_artifact(candidate)
                        except FileNotFoundError:
                            current_identity = None
                        except (OSError, ValueError):
                            continue
                        if current_identity is not None and _artifact_matches_record(
                            current_identity,
                            portable_record,
                        ):
                            try:
                                candidate.unlink()
                            except FileNotFoundError:
                                pass
                            except OSError:
                                logger.warning(
                                    "Could not remove uncommitted published file '%s'",
                                    candidate,
                                    exc_info=True,
                                )
                                continue

            if not _remove_portable_publication_file(portable, download_root_path):
                try:
                    if portable.exists():
                        continue
                except OSError:
                    continue

            if _remove_workspace(workspace):
                removed += 1
            continue

        legacy = _decode_legacy_staging_publication_marker(workspace, payload)
        if legacy is not None:
            staged, candidate, identity = legacy
            stat_dev, stat_ino = identity
            if not _path_is_within(candidate, download_root_path):
                logger.warning(
                    "Legacy temporary publication marker '%s' points outside the download root; preserving workspace for safety",
                    marker,
                )
                continue

            staged_identity = _same_file_identity(staged, stat_dev=stat_dev, stat_ino=stat_ino)
            candidate_identity = _same_file_identity(candidate, stat_dev=stat_dev, stat_ino=stat_ino)
            if candidate_identity is not None:
                if staged_identity is None:
                    logger.warning(
                        "Could not prove ownership of legacy published file '%s'; preserving workspace for safety",
                        candidate,
                    )
                    continue
                try:
                    artifact_identity = inspect_artifact(candidate)
                    committed = is_published_artifact(candidate, artifact_identity)
                except Exception:
                    logger.warning(
                        "Could not verify whether legacy staged download '%s' was committed; preserving workspace for safety",
                        candidate,
                        exc_info=True,
                    )
                    continue
                if not committed and not _unlink_if_identity(
                    candidate,
                    stat_dev=stat_dev,
                    stat_ino=stat_ino,
                ):
                    if _same_file_identity(candidate, stat_dev=stat_dev, stat_ino=stat_ino) is not None:
                        continue

            if _remove_workspace(workspace):
                removed += 1
            continue

        logger.warning(
            "Could not decode temporary publication marker '%s'; preserving workspace for safety",
            marker,
        )

    if removed:
        logger.warning(
            "Removed %s abandoned temporary download workspace(s) from a previous WireLoft process",
            removed,
        )
    return removed
