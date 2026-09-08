"""Persist filesystem identity for downloaded artifacts.

Revision ID: c1f7b9e4d205
Revises: e3a1b5c7d902
"""

from __future__ import annotations

import hashlib
import os
import stat
from typing import BinaryIO

from alembic import op
import sqlalchemy as sa


revision = "c1f7b9e4d205"
down_revision = "e3a1b5c7d902"
branch_labels = None
depends_on = None

_FINGERPRINT_SAMPLE_SIZE = 64 * 1024
_FINGERPRINT_VERSION = b"wireloft-artifact-v1\0"
_IDENTITY_CONSTRAINT = "ck_media_downloads_artifact_identity_complete"
_IDENTITY_CHECK = (
    "artifact_status = 'absent' OR ("
    "artifact_stat_dev IS NOT NULL AND length(artifact_stat_dev) > 0 AND "
    "artifact_stat_ino IS NOT NULL AND length(artifact_stat_ino) > 0 AND "
    "artifact_size_bytes IS NOT NULL AND artifact_size_bytes >= 0 AND "
    "artifact_fingerprint IS NOT NULL AND length(artifact_fingerprint) = 64"
    ")"
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
                f"artifact changed while fingerprinting: expected {read_size} bytes "
                f"at offset {offset}, read {len(chunk)}"
            )
        digest.update(offset.to_bytes(16, "big", signed=False))
        digest.update(read_size.to_bytes(8, "big", signed=False))
        digest.update(chunk)

    return digest.hexdigest()


def _inspect_artifact(path: str) -> tuple[str, str, int, str]:
    with open(path, "rb") as file:
        file_stat = os.fstat(file.fileno())
        if not stat.S_ISREG(file_stat.st_mode):
            raise ValueError("path is not a regular file")
        return (
            str(file_stat.st_dev),
            str(file_stat.st_ino),
            file_stat.st_size,
            _sampled_fingerprint(file, file_stat.st_size),
        )


def upgrade() -> None:
    connection = op.get_bind()
    downloads = connection.execute(
        sa.text(
            "SELECT id, file_path FROM media_downloads "
            "WHERE artifact_status != 'absent' ORDER BY id"
        )
    ).mappings().all()

    # Preflight every existing persistent artifact before making any schema
    # change. If one is already inconsistent, fail without leaving a partially
    # applied SQLite migration behind.
    identities: list[tuple[int, str, str, int, str]] = []
    for download in downloads:
        download_id = download["id"]
        path = download["file_path"]
        try:
            stat_dev, stat_ino, size_bytes, fingerprint = _inspect_artifact(path)
        except (OSError, ValueError) as exc:
            raise RuntimeError(
                f"Cannot backfill artifact identity for media download {download_id} "
                f"at {path!r}: {exc}. Restore, remove, or redownload the inconsistent "
                "artifact before retrying this migration."
            ) from exc
        identities.append((download_id, stat_dev, stat_ino, size_bytes, fingerprint))

    with op.batch_alter_table("media_downloads") as batch:
        batch.add_column(sa.Column("artifact_stat_dev", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("artifact_stat_ino", sa.String(length=32), nullable=True))
        batch.add_column(sa.Column("artifact_size_bytes", sa.BigInteger(), nullable=True))
        batch.add_column(sa.Column("artifact_fingerprint", sa.String(length=64), nullable=True))

    for download_id, stat_dev, stat_ino, size_bytes, fingerprint in identities:
        connection.execute(
            sa.text(
                "UPDATE media_downloads SET "
                "artifact_stat_dev = :stat_dev, "
                "artifact_stat_ino = :stat_ino, "
                "artifact_size_bytes = :size_bytes, "
                "artifact_fingerprint = :fingerprint "
                "WHERE id = :download_id"
            ),
            {
                "stat_dev": stat_dev,
                "stat_ino": stat_ino,
                "size_bytes": size_bytes,
                "fingerprint": fingerprint,
                "download_id": download_id,
            },
        )

    with op.batch_alter_table("media_downloads") as batch:
        batch.create_check_constraint(_IDENTITY_CONSTRAINT, _IDENTITY_CHECK)


def downgrade() -> None:
    with op.batch_alter_table("media_downloads") as batch:
        batch.drop_constraint(_IDENTITY_CONSTRAINT, type_="check")
        batch.drop_column("artifact_fingerprint")
        batch.drop_column("artifact_size_bytes")
        batch.drop_column("artifact_stat_ino")
        batch.drop_column("artifact_stat_dev")
