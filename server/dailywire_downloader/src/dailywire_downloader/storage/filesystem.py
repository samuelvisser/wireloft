"""Best-effort filesystem classification for storage planning and advisories.

The classifier intentionally reports only facts the operating system exposes. It
never benchmarks storage and never treats an unknown filesystem as local. Linux
mount metadata covers the normal Docker/NFS/CIFS cases; macOS/BSD mount output
and Windows drive types provide useful fallbacks for development installs.
"""
from __future__ import annotations

import ctypes
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path


class FilesystemStorageKind(StrEnum):
    LOCAL = "local"
    REMOTE = "remote"
    SHARED_OR_VIRTUAL = "shared_or_virtual"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class FilesystemInspection:
    path: Path
    existing_path: Path
    mount_point: Path | None
    filesystem_type: str | None
    storage_kind: FilesystemStorageKind


@dataclass(frozen=True)
class _Mount:
    mount_point: Path
    filesystem_type: str


_REMOTE_FILESYSTEMS = {
    "afs",
    "ceph",
    "cifs",
    "davfs",
    "fuse.davfs",
    "fuse.rclone",
    "fuse.sshfs",
    "glusterfs",
    "lustre",
    "nfs",
    "nfs4",
    "rclone",
    "smb3",
    "smbfs",
    "sshfs",
    "webdav",
}
_SHARED_OR_VIRTUAL_FILESYSTEMS = {
    "9p",
    "autofs",
    "fuse",
    "fuse.osxfs",
    "osxfuse",
    "vboxsf",
    "virtiofs",
    "vmhgfs",
}
_LOCAL_FILESYSTEMS = {
    "apfs",
    "btrfs",
    "exfat",
    "ext2",
    "ext3",
    "ext4",
    "f2fs",
    "hfs",
    "hfsplus",
    "jfs",
    "ntfs",
    "ntfs3",
    "overlay",
    "ramfs",
    "reiserfs",
    "squashfs",
    "tmpfs",
    "ufs",
    "vfat",
    "xfs",
    "zfs",
}
_MOUNTINFO_ESCAPE = re.compile(r"\\([0-7]{3})")


def classify_filesystem_type(filesystem_type: str | None) -> FilesystemStorageKind:
    if not filesystem_type:
        return FilesystemStorageKind.UNKNOWN
    normalized = filesystem_type.strip().lower()
    if normalized in _REMOTE_FILESYSTEMS:
        return FilesystemStorageKind.REMOTE
    if normalized in _SHARED_OR_VIRTUAL_FILESYSTEMS:
        return FilesystemStorageKind.SHARED_OR_VIRTUAL
    if normalized in _LOCAL_FILESYSTEMS:
        return FilesystemStorageKind.LOCAL
    if normalized.startswith("fuse."):
        return FilesystemStorageKind.SHARED_OR_VIRTUAL
    return FilesystemStorageKind.UNKNOWN


def _absolute_path(path: str | Path) -> Path:
    return Path(os.path.abspath(os.path.expanduser(os.fspath(path))))


def _existing_ancestor(path: Path) -> Path:
    candidate = path
    while candidate != candidate.parent:
        try:
            if candidate.exists():
                return candidate
        except OSError:
            pass
        candidate = candidate.parent
    return candidate


def _decode_mount_path(value: str) -> str:
    return _MOUNTINFO_ESCAPE.sub(lambda match: chr(int(match.group(1), 8)), value)


def _linux_mounts() -> list[_Mount]:
    try:
        text = Path("/proc/self/mountinfo").read_text(encoding="utf-8")
    except OSError:
        return []

    mounts: list[_Mount] = []
    for line in text.splitlines():
        before, separator, after = line.partition(" - ")
        if not separator:
            continue
        fields = before.split()
        details = after.split()
        if len(fields) < 5 or not details:
            continue
        mount_point = Path(_decode_mount_path(fields[4]))
        mounts.append(_Mount(mount_point, details[0].lower()))
    return mounts


def _unix_mounts_from_command() -> list[_Mount]:
    try:
        result = subprocess.run(
            ["mount"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=1,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if result.returncode != 0:
        return []

    mounts: list[_Mount] = []
    for line in result.stdout.splitlines():
        match = re.match(r"^.+? on (.+?) \(([^, )]+)", line)
        if match is None:
            continue
        mounts.append(_Mount(Path(match.group(1)), match.group(2).lower()))
    return mounts


def _path_is_within(path: Path, parent: Path) -> bool:
    try:
        os.path.commonpath((os.fspath(path), os.fspath(parent)))
    except (OSError, ValueError):
        return False
    try:
        return Path(os.path.commonpath((os.fspath(path), os.fspath(parent)))) == parent
    except (OSError, ValueError):
        return False


def _matching_mount(path: Path, mounts: list[_Mount]) -> _Mount | None:
    candidates = [mount for mount in mounts if _path_is_within(path, mount.mount_point)]
    if not candidates:
        return None
    return max(candidates, key=lambda mount: len(os.fspath(mount.mount_point)))


def _inspect_windows(path: Path, existing: Path) -> FilesystemInspection:
    anchor = existing.anchor or path.anchor
    mount_point = Path(anchor) if anchor else None
    if os.fspath(path).startswith(("\\\\", "//")):
        kind = FilesystemStorageKind.REMOTE
    elif mount_point is None:
        kind = FilesystemStorageKind.UNKNOWN
    else:
        try:
            drive_type = ctypes.windll.kernel32.GetDriveTypeW(str(mount_point))
        except (AttributeError, OSError):
            drive_type = 0
        if drive_type == 4:  # DRIVE_REMOTE
            kind = FilesystemStorageKind.REMOTE
        elif drive_type in {2, 3, 5, 6}:  # removable, fixed, optical, RAM disk
            kind = FilesystemStorageKind.LOCAL
        else:
            kind = FilesystemStorageKind.UNKNOWN
    return FilesystemInspection(path, existing, mount_point, None, kind)


def inspect_filesystem(path: str | Path) -> FilesystemInspection:
    """Classify the filesystem containing *path* without creating the path."""
    requested = _absolute_path(path)
    existing = _existing_ancestor(requested)

    if os.name == "nt":
        return _inspect_windows(requested, existing)

    mounts = _linux_mounts() if sys.platform.startswith("linux") else _unix_mounts_from_command()
    mount = _matching_mount(existing, mounts)
    if mount is None:
        return FilesystemInspection(
            requested,
            existing,
            None,
            None,
            FilesystemStorageKind.UNKNOWN,
        )
    return FilesystemInspection(
        requested,
        existing,
        mount.mount_point,
        mount.filesystem_type,
        classify_filesystem_type(mount.filesystem_type),
    )


def same_filesystem(first: str | Path, second: str | Path) -> bool | None:
    """Return whether two paths resolve to the same filesystem, when knowable."""
    try:
        first_existing = _existing_ancestor(_absolute_path(first))
        second_existing = _existing_ancestor(_absolute_path(second))
        return first_existing.stat().st_dev == second_existing.stat().st_dev
    except OSError:
        return None
