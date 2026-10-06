"""Collision-safe auxiliary publication and crash-recovery ownership records."""
from __future__ import annotations

import json
import os
import shutil
from dataclasses import asdict
from pathlib import Path
from time import sleep
from typing import Callable
from uuid import uuid4

from ..errors import DownloadCancelled, DownloadError
from ..hls_bundle import hls_asset_marker, hls_asset_root
from ..models import DownloadProgress
from .copying import copy_file
from .claims import DownloadPathClaimJournal
from .helpers import _path_is_within
from .identity import ArtifactIdentity, inspect_artifact

_JOURNAL = ".wireloft-auxiliary-publication"
_MAGIC = "wireloft-auxiliary-publication-v1"


def _matches(path: Path, identity: dict) -> bool:
    try:
        current = inspect_artifact(path)
        return current.size_bytes == identity["size_bytes"] and current.fingerprint == identity["fingerprint"]
    except (FileNotFoundError, ValueError, OSError, KeyError):
        return False


def _write_record(workspace: Path, record: dict) -> None:
    temporary = workspace / (_JOURNAL + ".part")
    with temporary.open("w", encoding="utf-8") as out:
        json.dump(record, out, separators=(",", ":"))
        out.flush()
        os.fsync(out.fileno())
    os.replace(temporary, workspace / _JOURNAL)


class PublicationJournal:
    def __init__(
        self,
        workspace: Path,
        media_path: Path,
        *,
        path_claims: DownloadPathClaimJournal | None = None,
    ):
        self.workspace = workspace
        self.media_path = media_path
        self.path_claims = path_claims
        self.record = {
            "format": _MAGIC,
            "media_path": str(media_path.absolute()),
            "media_identity": asdict(inspect_artifact(media_path)),
            "files": [],
        }
        self._write()

    def _write(self) -> None:
        _write_record(self.workspace, self.record)

    def publish(
        self, source: Path, suffix: str, *,
        progress: Callable[[DownloadProgress], None], should_cancel: Callable[[], bool],
    ) -> Path:
        from .temporary import _claim_publication_lock, _publish_complete_file

        destination = self.media_path.with_name(self.media_path.stem + suffix)
        if destination == self.media_path or "/" in suffix or "\\" in suffix or ".." in suffix:
            raise DownloadError("Invalid auxiliary publication destination")
        portable = destination.parent / f".wireloft-publish-{uuid4().hex}.part"
        entry = {"path": str(destination.absolute()), "portable": str(portable.absolute()), "identity": None}
        self.record["files"].append(entry)
        self._write()
        copy_file(source, portable, progress=progress, should_cancel=should_cancel)
        entry["identity"] = asdict(inspect_artifact(portable))
        self._write()
        while True:
            if should_cancel():
                raise DownloadCancelled("Canceled while publishing a sidecar")
            lock = _claim_publication_lock(
                destination,
                path_claims=self.path_claims,
            )
            if lock is not None:
                break
            sleep(0.05)
        try:
            _publish_complete_file(portable, destination)
        finally:
            lock.release()
        return destination

    def rollback(self) -> None:
        _rollback_record(self.record, self.media_path.parent, self._write)


def _rollback_record(record: dict, root: Path, persist: Callable[[], None]) -> None:
    for entry in record["files"]:
        path = Path(entry["path"])
        portable = Path(entry["portable"])
        if not _path_is_within(path, root) or not _path_is_within(portable, root):
            raise ValueError("Unsafe auxiliary publication record")
        if not (portable.name.startswith(".wireloft-publish-") and portable.name.endswith(".part")):
            raise ValueError("Unsafe auxiliary staging path")
        # If the portable file still exists, our final rename never happened.
        # Never remove somebody else's colliding destination in that case.
        if portable.exists() and not entry.get("aborted"):
            # Persist the failed-rename proof before removing its portable file.
            # Recovery can itself be interrupted; absence alone is not proof on
            # its next run once a rollback has consumed that portable file.
            entry["aborted"] = True
            persist()
        if not entry.get("aborted") and not portable.exists() and entry["identity"] and _matches(path, entry["identity"]):
            path.unlink(missing_ok=True)
        portable.unlink(missing_ok=True)


def reconcile_publication_journal(
    workspace: Path, download_root: Path,
    is_committed: Callable[[Path, ArtifactIdentity], bool],
) -> bool:
    """Reconcile only provably owned outputs. False means preserve for inspection."""
    journal = workspace / _JOURNAL
    if not journal.exists():
        return True
    try:
        if journal.stat().st_size > 1024 * 1024:
            return False
        record = json.loads(journal.read_text(encoding="utf-8"))
        if record["format"] != _MAGIC:
            return False
        media = Path(record["media_path"])
        if not _path_is_within(media, download_root):
            return False
        identity = ArtifactIdentity(**record["media_identity"])
        if is_committed(media, identity):
            # Preserve committed outputs even when external changes have altered
            # an inode or deleted the main file since the application committed.
            for entry in record["files"]:
                portable = Path(entry["portable"])
                if not _path_is_within(portable, download_root) or not portable.name.startswith(".wireloft-publish-"):
                    return False
                portable.unlink(missing_ok=True)
        else:
            _rollback_record(record, download_root, lambda: _write_record(workspace, record))
            if _matches(media, record["media_identity"]):
                media.unlink()
                if media.suffix == ".m3u8" and hls_asset_marker(media).is_file():
                    shutil.rmtree(hls_asset_root(media))
        return True
    except (OSError, ValueError, KeyError, TypeError):
        return False
