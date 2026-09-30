from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
import stat
from typing import BinaryIO


_FINGERPRINT_SAMPLE_SIZE = 64 * 1024
_FINGERPRINT_VERSION = b"wireloft-artifact-v1\0"


@dataclass(frozen=True)
class ArtifactIdentity:
    """Filesystem and content identity for one persistent media artifact."""

    stat_dev: str
    stat_ino: str
    size_bytes: int
    fingerprint: str


def inspect_artifact(path: str | os.PathLike[str]) -> ArtifactIdentity:
    """Return a stable hybrid identity for a regular file.

    Device/inode values are a cheap rename fast path on filesystems that expose
    stable identifiers. The sampled SHA-256 fingerprint is the portable fallback
    for filesystems or network mounts where those identifiers can change.
    """
    with open(path, "rb") as file:
        file_stat = os.fstat(file.fileno())
        if not stat.S_ISREG(file_stat.st_mode):
            raise ValueError(f"Expected a regular file at '{os.fspath(path)}'")
        return ArtifactIdentity(
            stat_dev=str(file_stat.st_dev),
            stat_ino=str(file_stat.st_ino),
            size_bytes=file_stat.st_size,
            fingerprint=_sampled_fingerprint(file, file_stat.st_size),
        )


def _sampled_fingerprint(file: BinaryIO, size_bytes: int) -> str:
    digest = hashlib.sha256()
    digest.update(_FINGERPRINT_VERSION)
    digest.update(size_bytes.to_bytes(16, "big", signed=False))

    if size_bytes <= _FINGERPRINT_SAMPLE_SIZE * 3:
        offsets = (0,)
        read_sizes = (size_bytes,)
    else:
        middle_offset = max(0, (size_bytes - _FINGERPRINT_SAMPLE_SIZE) // 2)
        offsets = (0, middle_offset, size_bytes - _FINGERPRINT_SAMPLE_SIZE)
        read_sizes = (_FINGERPRINT_SAMPLE_SIZE,) * 3

    for offset, read_size in zip(offsets, read_sizes, strict=True):
        file.seek(offset)
        chunk = file.read(read_size)
        if len(chunk) != read_size:
            raise OSError(
                f"Artifact changed while fingerprinting: expected {read_size} bytes "
                f"at offset {offset}, read {len(chunk)}"
            )
        digest.update(offset.to_bytes(16, "big", signed=False))
        digest.update(read_size.to_bytes(8, "big", signed=False))
        digest.update(chunk)

    return digest.hexdigest()
