from __future__ import annotations

from pathlib import Path

from dailywire_downloader.storage.filesystem import (
    FilesystemStorageKind,
    _Mount,
    _decode_mount_path,
    _matching_mount,
    classify_filesystem_type,
)


def test_filesystem_type_classification():
    assert classify_filesystem_type("ext4") is FilesystemStorageKind.LOCAL
    assert classify_filesystem_type("overlay") is FilesystemStorageKind.LOCAL
    assert classify_filesystem_type("nfs4") is FilesystemStorageKind.REMOTE
    assert classify_filesystem_type("cifs") is FilesystemStorageKind.REMOTE
    assert classify_filesystem_type("virtiofs") is FilesystemStorageKind.SHARED_OR_VIRTUAL
    assert classify_filesystem_type("fuse.custom") is FilesystemStorageKind.SHARED_OR_VIRTUAL
    assert classify_filesystem_type("something-new") is FilesystemStorageKind.UNKNOWN


def test_mountinfo_path_escapes_are_decoded():
    assert _decode_mount_path(r"/media/My\040Library") == "/media/My Library"


def test_longest_matching_mount_wins():
    mounts = [
        _Mount(Path("/"), "ext4"),
        _Mount(Path("/downloads"), "nfs4"),
        _Mount(Path("/downloads/local"), "ext4"),
    ]

    assert _matching_mount(Path("/downloads/movie.mp4"), mounts).filesystem_type == "nfs4"
    assert _matching_mount(Path("/downloads/local/movie.mp4"), mounts).filesystem_type == "ext4"
