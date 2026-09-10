from __future__ import annotations

import errno
import hashlib
import logging
import os
import shutil
import stat
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from itertools import count
from pathlib import Path

logger = logging.getLogger(__name__)

_RESERVATION_MARKER_PREFIX = ".wireloft-download-reservation-"
_RESERVATION_MARKER_MAGIC = b"WIRELOFT_DOWNLOAD_PATH_RESERVATION_V1\0"
_MAX_MARKER_BYTES = 8192
_STAGING_DIRECTORY_NAME = ".wireloft-staging"
_STAGING_WORKSPACE_PREFIX = "attempt-"
_STAGING_PUBLICATION_MARKER = ".wireloft-publication"
_STAGING_PUBLICATION_MAGIC = b"WIRELOFT_STAGED_DOWNLOAD_PUBLICATION_V1\0"


class TemporaryDownloadFilesystemError(RuntimeError):
    """Raised when temporary staging cannot safely publish to the destination."""


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


def _numbered_candidate(requested: Path, number: int) -> Path:
    if number == 0:
        return requested
    return requested.with_name(f"{requested.stem}-{number}{requested.suffix}")


def _nearest_existing_directory(path: Path) -> Path:
    candidate = path
    while True:
        try:
            current = candidate.stat()
        except FileNotFoundError:
            parent = candidate.parent
            if parent == candidate:
                raise TemporaryDownloadFilesystemError(
                    f"No existing parent directory is available for '{path}'."
                )
            candidate = parent
            continue
        except OSError as exc:
            raise TemporaryDownloadFilesystemError(
                f"Could not inspect destination parent '{candidate}': {exc}"
            ) from exc

        if not stat.S_ISDIR(current.st_mode):
            raise TemporaryDownloadFilesystemError(
                f"Destination parent path '{candidate}' is not a directory."
            )
        return candidate


def _path_is_within(path: Path, root: Path) -> bool:
    absolute_path = Path(os.path.abspath(path))
    absolute_root = Path(os.path.abspath(root))
    try:
        absolute_path.relative_to(absolute_root)
    except ValueError:
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


def create_temporary_download_workspace(
    temporary_root: str | Path,
    requested_destination: str | Path,
) -> TemporaryDownloadWorkspace:
    """Create a private staging path that can be published atomically later.

    The workspace is created before any network transfer begins. Temporary mode
    deliberately requires staging and destination directories to be on the same
    filesystem/volume: that lets ``publish_temporary_download`` expose the fully
    completed file in one atomic filesystem operation without ever creating an
    empty or partially copied final file. The final directory itself is not
    created until publication time.
    """
    requested = Path(requested_destination)
    destination_anchor = _nearest_existing_directory(requested.parent)

    staging_root = Path(temporary_root) / _STAGING_DIRECTORY_NAME
    staging_root.mkdir(parents=True, exist_ok=True)
    workspace = Path(tempfile.mkdtemp(prefix=_STAGING_WORKSPACE_PREFIX, dir=staging_root))

    try:
        if workspace.stat().st_dev != destination_anchor.stat().st_dev:
            raise TemporaryDownloadFilesystemError(
                "Temporary download folder and final download destination must be on the same "
                "filesystem or volume so WireLoft can publish completed files atomically."
            )
    except BaseException:
        try:
            shutil.rmtree(workspace)
        except OSError:
            pass
        raise

    staged_path = workspace / f"download{requested.suffix}"
    return TemporaryDownloadWorkspace(path=staged_path, workspace=workspace)


def _write_staging_publication_marker(
    staged: Path,
    candidate: Path,
    staged_stat: os.stat_result,
) -> None:
    marker = staged.parent / _STAGING_PUBLICATION_MARKER
    candidate_path = Path(os.path.abspath(candidate))
    payload = (
        _STAGING_PUBLICATION_MAGIC
        + os.fsencode(staged.name)
        + b"\0"
        + os.fsencode(candidate_path)
        + b"\0"
        + f"{staged_stat.st_dev}:{staged_stat.st_ino}".encode("ascii")
    )
    if len(payload) > _MAX_MARKER_BYTES:
        raise TemporaryDownloadFilesystemError(
            "Temporary download publication path is too long to record safely."
        )

    fd = os.open(marker, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        _write_all(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)


def _decode_staging_publication_marker(
    workspace: Path,
    payload: bytes,
) -> tuple[Path, Path, tuple[int, int]] | None:
    if not payload.startswith(_STAGING_PUBLICATION_MAGIC):
        return None

    encoded = payload[len(_STAGING_PUBLICATION_MAGIC):]
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


def publish_temporary_download(
    staged_path: str | Path,
    requested_destination: str | Path,
) -> Path:
    """Publish a completed staged file under the first unused exact filename.

    ``os.link`` provides the important no-overwrite property without a placeholder:
    a complete file appears at the destination atomically, and an existing entry
    causes ``EEXIST`` so the next numbered candidate can be attempted safely even
    when multiple workers finish at the same time.

    The staging hard link and a private publication marker remain until the caller
    commits the completed artifact to the database. If WireLoft dies in that tiny
    window, startup recovery can prove whether the final link was committed and
    either preserve it or remove the orphan safely.
    """
    staged = Path(staged_path)
    requested = Path(requested_destination)
    requested.parent.mkdir(parents=True, exist_ok=True)

    try:
        staged_stat = staged.stat()
        if not stat.S_ISREG(staged_stat.st_mode):
            raise TemporaryDownloadFilesystemError(
                f"Completed temporary download is not a regular file: {staged}"
            )
        if staged_stat.st_dev != requested.parent.stat().st_dev:
            raise TemporaryDownloadFilesystemError(
                "Temporary download folder and final download destination must be on the same "
                "filesystem or volume so WireLoft can publish completed files atomically."
            )
    except FileNotFoundError as exc:
        raise TemporaryDownloadFilesystemError(
            f"Completed temporary download no longer exists: {staged}"
        ) from exc

    for number in count(0):
        candidate = _numbered_candidate(requested, number)
        _write_staging_publication_marker(staged, candidate, staged_stat)
        try:
            os.link(staged, candidate)
        except FileExistsError:
            continue
        except OSError as exc:
            if exc.errno == errno.EXDEV:
                raise TemporaryDownloadFilesystemError(
                    "Temporary download folder and final download destination must be on the same "
                    "filesystem or volume so WireLoft can publish completed files atomically."
                ) from exc
            raise TemporaryDownloadFilesystemError(
                f"Could not publish completed temporary download to '{candidate}': {exc}"
            ) from exc
        return candidate

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


def cleanup_abandoned_temporary_downloads(
    temporary_root: str | Path,
    download_root: str | Path,
    *,
    is_published_artifact: Callable[[Path, int, int], bool],
) -> int:
    """Reconcile private staging workspaces left by an unclean shutdown.

    A workspace without a complete publication marker cannot have published a
    final file, because the marker is fsynced before the no-overwrite hard link is
    attempted. A complete marker lets recovery compare both links by filesystem
    identity. If the database already committed that exact artifact, the final
    file is preserved; otherwise the orphaned final link is removed so a recovered
    download can reuse the intended filename.
    """
    staging_root = Path(temporary_root) / _STAGING_DIRECTORY_NAME
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

        if len(payload) > _MAX_MARKER_BYTES:
            logger.warning(
                "Temporary download publication marker '%s' is too large; preserving workspace for safety",
                marker,
            )
            continue

        decoded = _decode_staging_publication_marker(workspace, payload) if payload else None
        if decoded is not None:
            staged, candidate, identity = decoded
            stat_dev, stat_ino = identity
            if not _path_is_within(candidate, Path(download_root)):
                logger.warning(
                    "Temporary download publication marker '%s' points outside the download root; preserving workspace for safety",
                    marker,
                )
                continue

            staged_identity = _same_file_identity(
                staged,
                stat_dev=stat_dev,
                stat_ino=stat_ino,
            )
            candidate_identity = _same_file_identity(
                candidate,
                stat_dev=stat_dev,
                stat_ino=stat_ino,
            )

            if candidate_identity is not None:
                if staged_identity is None:
                    logger.warning(
                        "Could not prove ownership of published temporary file '%s'; preserving workspace for safety",
                        candidate,
                    )
                    continue
                try:
                    committed = is_published_artifact(candidate, stat_dev, stat_ino)
                except Exception:
                    logger.warning(
                        "Could not verify whether staged download '%s' was committed; preserving workspace for safety",
                        candidate,
                        exc_info=True,
                    )
                    continue

                if not committed and not _unlink_if_identity(
                    candidate,
                    stat_dev=stat_dev,
                    stat_ino=stat_ino,
                ):
                    # A disappearance is harmless; a still-matching entry means
                    # deletion failed and the marker must survive for another try.
                    if _same_file_identity(candidate, stat_dev=stat_dev, stat_ino=stat_ino) is not None:
                        continue

        if _remove_workspace(workspace):
            removed += 1

    if removed:
        logger.warning(
            "Removed %s abandoned temporary download workspace(s) from a previous WireLoft process",
            removed,
        )
    return removed
