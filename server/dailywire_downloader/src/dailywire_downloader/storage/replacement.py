"""Crash-recoverable, in-place publication of a completed replacement.

The download coordinator owns transfer/processing. This module extends the
existing filesystem publication workflow: finished files are staged next to
their final paths, and a durable journal is written *before* any os.replace.
On startup the ordinary download filesystem recovery replays these journals.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from uuid import uuid4

from ..errors import DownloadCancelled, DownloadError
from ..hls_bundle import hls_asset_marker, hls_asset_root
from ..models import DownloadProgress
from .helpers import _path_is_within
from .identity import ArtifactIdentity, inspect_artifact

logger = logging.getLogger(__name__)

_FORMAT = "wireloft-replacement-v1"
_JOURNAL_RE = re.compile(r"^\.wireloft-replacement-([0-9a-f]{32})\.json$")
_STAGE_RE = re.compile(r"^\.wireloft-replace-([0-9a-f]{32})\.part$")
_MAX_JOURNAL_BYTES = 1024 * 1024


@dataclass(frozen=True)
class OwnedFile:
    path: Path
    identity: ArtifactIdentity


@dataclass(frozen=True)
class PreviousDownload:
    media: OwnedFile
    assets: tuple[OwnedFile, ...]


@dataclass(frozen=True)
class ReplacementSidecar:
    asset_key: str
    kind: str
    source: Path
    suffix: str


def _matches(path: Path, identity: dict | ArtifactIdentity) -> bool:
    try:
        current = inspect_artifact(path)
    except (OSError, ValueError):
        return False
    expected = asdict(identity) if isinstance(identity, ArtifactIdentity) else identity
    return (
        current.size_bytes == expected["size_bytes"]
        and current.fingerprint == expected["fingerprint"]
    )


def capture_previous_download(
    media_path: str,
    *,
    size_bytes: int | None,
    fingerprint: str | None,
    assets: tuple[tuple[str, int | None, str | None], ...],
) -> PreviousDownload | None:
    """Only claim previous files whose content matches recorded ownership."""
    path = Path(media_path)
    if path.suffix == ".ext" or size_bytes is None or not fingerprint:
        return None
    try:
        media = OwnedFile(path, inspect_artifact(path))
    except (OSError, ValueError):
        return None
    if media.identity.size_bytes != size_bytes or media.identity.fingerprint != fingerprint:
        return None

    sidecars: list[OwnedFile] = []
    for asset_path, size, asset_fingerprint in assets:
        if size is None or not asset_fingerprint:
            continue
        try:
            asset = OwnedFile(Path(asset_path), inspect_artifact(asset_path))
        except (OSError, ValueError):
            continue
        if asset.identity.size_bytes == size and asset.identity.fingerprint == asset_fingerprint:
            sidecars.append(asset)
    return PreviousDownload(media, tuple(sidecars))


def _sync_directory(directory: Path) -> None:
    """Best-effort durability on filesystems supporting directory fsync."""
    if os.name == "nt":
        return
    try:
        fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        logger.debug("Directory fsync is unsupported for '%s'", directory, exc_info=True)


def _write_record(path: Path, record: dict) -> None:
    temporary = path.with_name(path.name + ".part")
    try:
        with temporary.open("x", encoding="utf-8") as stream:
            json.dump(record, stream, separators=(",", ":"), sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        _sync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _stage_completed_file(
    source: Path, destination: Path, *,
    should_cancel: Callable[[], bool],
    progress: Callable[[DownloadProgress], None] | None,
) -> tuple[Path, ArtifactIdentity]:
    from .temporary import _copy_completed_file

    staged = destination.parent / f".wireloft-replace-{uuid4().hex}.part"
    expected = inspect_artifact(source)
    try:
        _copy_completed_file(
            source, staged, should_cancel=should_cancel, progress=progress,
        )
        identity = inspect_artifact(staged)
        if (identity.size_bytes, identity.fingerprint) != (
            expected.size_bytes, expected.fingerprint,
        ):
            raise DownloadError(f"Replacement changed while staging '{destination}'")
        with staged.open("rb") as stream:
            os.fsync(stream.fileno())
        return staged, identity
    except BaseException:
        staged.unlink(missing_ok=True)
        raise


def _validate_target(path: Path, old: ArtifactIdentity | None) -> None:
    if path.is_symlink():
        raise DownloadError(f"Replacement destination is a symbolic link: '{path}'")
    if old is not None:
        if not _matches(path, old):
            raise DownloadError(f"Existing replacement destination changed: '{path}'")
    elif path.exists() or path.is_symlink():
        raise DownloadError(f"Replacement would overwrite an unrelated file: '{path}'")


@dataclass
class ReplacementJournal:
    path: Path
    record: dict

    @property
    def media_path(self) -> Path:
        return Path(self.record["media"]["path"])

    def discard_unpublished(self) -> None:
        """Remove the journal only when no final path has been replaced."""
        files = [*self.record["assets"], self.record["media"]]
        if all(
            _matches(Path(item["path"]), item["old"]) if item["old"] is not None
            else not Path(item["path"]).exists()
            for item in files
        ):
            for item in files:
                Path(item["staged"]).unlink(missing_ok=True)
            self.path.unlink(missing_ok=True)
            _sync_directory(self.path.parent)

    def cleanup_committed(self) -> None:
        """Drop obsolete assets only after the database commit is durable."""
        _cleanup_committed_record(self.path, self.record)


def publish_replacement(
    *,
    media_download_id: int,
    previous: PreviousDownload,
    media_source: Path,
    sidecars: tuple[ReplacementSidecar, ...],
    downloaded_bytes: int,
    format_downloaded: str,
    downloaded_publish_status: str | None,
    should_cancel: Callable[[], bool],
    progress: Callable[[DownloadProgress], None] | None = None,
) -> tuple[ReplacementJournal, ArtifactIdentity, tuple[tuple[ReplacementSidecar, Path, ArtifactIdentity], ...]]:
    """Publish ready files without ever removing or renaming the old media path.

    A durable record is stored on the *destination* filesystem before any
    replacement. This survives loss of an ephemeral Docker temporary directory.
    """
    media = previous.media
    destination = media.path
    destination.parent.mkdir(parents=True, exist_ok=True)
    old_assets = {asset.path: asset.identity for asset in previous.assets}
    staged_paths: list[Path] = []
    record_written = False
    journal_path = destination.parent / f".wireloft-replacement-{uuid4().hex}.json"
    try:
        _validate_target(destination, media.identity)
        entries: list[dict] = []
        published_assets = []
        destinations: set[Path] = {destination}
        for sidecar in sidecars:
            path = destination.with_name(destination.stem + sidecar.suffix)
            if path in destinations or "/" in sidecar.suffix or "\\" in sidecar.suffix:
                raise DownloadError("Replacement sidecar destination collision")
            destinations.add(path)
            previous_identity = old_assets.get(path)
            _validate_target(path, previous_identity)
            staged, identity = _stage_completed_file(
                sidecar.source, path, should_cancel=should_cancel, progress=None,
            )
            staged_paths.append(staged)
            entries.append({
                "path": str(path.absolute()), "staged": str(staged.absolute()),
                "old": asdict(previous_identity) if previous_identity else None,
                "new": asdict(identity), "asset_key": sidecar.asset_key,
                "kind": sidecar.kind, "suffix": sidecar.suffix,
            })
            published_assets.append((sidecar, path, identity))

        staged_media, new_media_identity = _stage_completed_file(
            media_source, destination, should_cancel=should_cancel, progress=progress,
        )
        staged_paths.append(staged_media)
        if new_media_identity.size_bytes <= 0:
            raise DownloadError("Replacement media is empty")
        media_entry = {
            "path": str(destination.absolute()),
            "staged": str(staged_media.absolute()),
            "old": asdict(media.identity),
            "new": asdict(new_media_identity),
        }
        record = {
            "format": _FORMAT,
            "media_download_id": media_download_id,
            "media": media_entry,
            "assets": entries,
            "obsolete_assets": [
                {"path": str(item.path.absolute()), "identity": asdict(item.identity)}
                for item in previous.assets if item.path not in destinations
            ],
            "downloaded_bytes": downloaded_bytes,
            "format_downloaded": format_downloaded,
            "downloaded_publish_status": downloaded_publish_status,
            "downloaded_at": datetime.now(timezone.utc).isoformat(),
        }

        if should_cancel():
            raise DownloadCancelled("Canceled before replacing the existing file")

        # Check every previous target again immediately before publication. No
        # unrelated file should be overwritten if the filesystem changed during
        # the potentially long destination-side copy.
        for item in [*entries, media_entry]:
            _validate_target(
                Path(item["path"]),
                ArtifactIdentity(**item["old"]) if item["old"] else None,
            )
        _write_record(journal_path, record)
        record_written = True
        publication = ReplacementJournal(journal_path, record)

        # Sidecars first, main media last. Crash recovery replays either stage
        # independently, checking both old and new identities before modifying.
        for entry in [*entries, media_entry]:
            os.replace(entry["staged"], entry["path"])
            _sync_directory(destination.parent)
        return publication, inspect_artifact(destination), tuple(published_assets)
    except BaseException:
        if record_written:
            # Once any final path changed the journal must survive. If no
            # replacement happened this safely discards a cancelled attempt.
            ReplacementJournal(journal_path, record).discard_unpublished()
        else:
            for path in staged_paths:
                path.unlink(missing_ok=True)
        raise


def _validate_identity(raw: object) -> bool:
    return (
        isinstance(raw, dict)
        and isinstance(raw.get("size_bytes"), int)
        and raw["size_bytes"] >= 0
        and isinstance(raw.get("fingerprint"), str)
        and bool(re.fullmatch(r"[0-9a-f]{64}", raw["fingerprint"]))
        and isinstance(raw.get("stat_dev"), str)
        and isinstance(raw.get("stat_ino"), str)
    )


def _load_record(journal: Path, root: Path) -> dict | None:
    try:
        if journal.is_symlink() or journal.stat().st_size > _MAX_JOURNAL_BYTES:
            return None
        record = json.loads(journal.read_text(encoding="utf-8"))
        if not isinstance(record, dict) or record.get("format") != _FORMAT:
            return None
        if type(record.get("media_download_id")) is not int or record["media_download_id"] <= 0:
            return None
        if type(record.get("downloaded_bytes")) is not int or record["downloaded_bytes"] < 0:
            return None
        if not isinstance(record.get("format_downloaded"), str):
            return None
        if not isinstance(record.get("downloaded_at"), str):
            return None
        recorded_at = datetime.fromisoformat(record["downloaded_at"])
        if recorded_at.tzinfo is None or recorded_at.utcoffset() is None:
            return None
        if not (record.get("downloaded_publish_status") is None or isinstance(record["downloaded_publish_status"], str)):
            return None
        main = record.get("media")
        assets = record.get("assets")
        obsolete = record.get("obsolete_assets")
        if not isinstance(main, dict) or not isinstance(assets, list) or len(assets) > 64:
            return None
        if not isinstance(obsolete, list) or len(obsolete) > 64:
            return None
        if not _validate_identity(main.get("old")):
            return None
        if not all(isinstance(item, dict) for item in [main, *assets, *obsolete]):
            return None

        final = Path(main.get("path", ""))
        if not final.is_absolute() or final.parent != journal.parent or not _path_is_within(final, root):
            return None
        claimed: set[Path] = set()
        staged_paths: set[Path] = set()
        asset_keys: set[str] = set()
        for item in [*assets, main]:
            path_text, stage_text = item.get("path"), item.get("staged")
            if not isinstance(path_text, str) or not isinstance(stage_text, str):
                return None
            target, staged = Path(path_text), Path(stage_text)
            if not target.is_absolute() or not staged.is_absolute() or target.parent != final.parent or staged.parent != final.parent:
                return None
            if target in claimed or staged in staged_paths:
                return None
            if not _path_is_within(target, root) or _STAGE_RE.fullmatch(staged.name) is None:
                return None
            if staged.is_symlink() or target.is_symlink():
                return None
            if not _validate_identity(item.get("new")):
                return None
            if item.get("old") is not None and not _validate_identity(item["old"]):
                return None
            claimed.add(target)
            staged_paths.add(staged)
            if item is not main:
                key, kind, suffix = item.get("asset_key"), item.get("kind"), item.get("suffix")
                if not isinstance(key, str) or not key or key in asset_keys or not isinstance(kind, str):
                    return None
                if not isinstance(suffix, str) or not suffix.startswith(".") or "/" in suffix or "\\" in suffix or ".." in suffix:
                    return None
                if target != final.with_name(final.stem + suffix):
                    return None
                asset_keys.add(key)
        for item in obsolete:
            path_text = item.get("path")
            if not isinstance(path_text, str) or not _validate_identity(item.get("identity")):
                return None
            path = Path(path_text)
            if not path.is_absolute() or not _path_is_within(path, root):
                return None
            if path.is_symlink() or path in claimed or path == final:
                return None
        return record
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        return None


def _replay_record(record: dict) -> bool:
    entries = [*record["assets"], record["media"]]
    # Preflight *all* targets before changing even one. A mismatched external
    # file must never be overwritten by a recovery attempt.
    for item in entries:
        target, staged = Path(item["path"]), Path(item["staged"])
        if _matches(target, item["new"]):
            continue
        if item["old"] is not None:
            if not _matches(target, item["old"]):
                return False
        elif target.exists() or target.is_symlink():
            return False
        if not _matches(staged, item["new"]):
            return False

    for item in entries:
        target, staged = Path(item["path"]), Path(item["staged"])
        if _matches(target, item["new"]):
            continue
        os.replace(staged, target)
        _sync_directory(target.parent)
    return True


def _cleanup_committed_record(journal: Path, record: dict) -> None:
    for item in record["obsolete_assets"]:
        path = Path(item["path"])
        if _matches(path, item["identity"]):
            path.unlink(missing_ok=True)
    for item in [*record["assets"], record["media"]]:
        staged = Path(item["staged"])
        if _matches(staged, item["new"]):
            staged.unlink(missing_ok=True)
    journal.unlink(missing_ok=True)
    _sync_directory(journal.parent)


def retire_superseded_files(
    previous: PreviousDownload,
    *,
    retained_paths: frozenset[str],
) -> None:
    """Retire former media only after a successful, durable replacement commit."""
    media = previous.media
    if str(media.path) not in retained_paths:
        # A moved or externally changed file is not ours to delete. Preserve
        # its associated sidecars if the identity check fails.
        if not _matches(media.path, media.identity):
            return
        try:
            media.path.unlink()
            if media.path.suffix.lower() == ".m3u8" and hls_asset_marker(media.path).is_file():
                shutil.rmtree(hls_asset_root(media.path))
        except OSError:
            logger.warning("Could not remove superseded media '%s'", media.path, exc_info=True)
    for asset in previous.assets:
        if str(asset.path) not in retained_paths and _matches(asset.path, asset.identity):
            try:
                asset.path.unlink()
            except OSError:
                logger.warning("Could not remove superseded sidecar '%s'", asset.path, exc_info=True)


def reconcile_abandoned_replacements(
    download_root: str | Path,
    *,
    recover: Callable[[dict, Callable[[], bool]], bool],
) -> int:
    """Extend the existing startup filesystem recovery for in-place publication.

    Refuse uncertain states and preserve their records for manual inspection.
    No separate scheduler, migration runner or background worker is involved.
    """
    root = Path(download_root)
    if not root.is_dir():
        return 0
    recovered = 0
    referenced: set[Path] = set()
    invalid_directories: set[Path] = set()
    journals: list[Path] = []

    def onerror(error: OSError) -> None:
        logger.warning("Could not scan replacement publication records: %s", error)

    for directory, _subdirs, filenames in os.walk(root, followlinks=False, onerror=onerror):
        parent = Path(directory)
        for filename in filenames:
            if _JOURNAL_RE.fullmatch(filename):
                journals.append(parent / filename)
    for journal in journals:
        record = _load_record(journal, root)
        if record is None:
            invalid_directories.add(journal.parent)
            logger.warning("Preserving invalid replacement journal '%s'", journal)
            continue
        entries = [*record["assets"], record["media"]]
        referenced.update(Path(item["staged"]) for item in entries)
        try:
            # Application verifies database ownership *before* applying any
            # filesystem changes, then persists the new identity. An interrupted
            # database commit is recoverable by replaying this same journal.
            if not recover(record, lambda: _replay_record(record)):
                logger.warning("Replacement journal '%s' could not be reconciled safely", journal)
                continue
            _cleanup_committed_record(journal, record)
            recovered += 1
        except Exception:
            # One invalid journal or database failure must not prevent other
            # independent artifacts from being recovered in the same startup.
            logger.warning("Could not complete replacement recovery '%s'", journal, exc_info=True)

    # A crash before the journal was written can leave a complete or partial
    # destination-side .part file. It cannot have replaced any final file yet.
    for directory, _subdirs, filenames in os.walk(root, followlinks=False, onerror=onerror):
        parent = Path(directory)
        if parent in invalid_directories:
            continue
        for filename in filenames:
            if _JOURNAL_RE.fullmatch(filename[:-5]) and filename.endswith(".json.part"):
                partial = parent / filename
                try:
                    if not partial.is_symlink() and partial.is_file():
                        partial.unlink()
                except OSError:
                    logger.warning("Could not remove incomplete replacement journal '%s'", partial, exc_info=True)
                continue
            if not _STAGE_RE.fullmatch(filename):
                continue
            candidate = parent / filename
            if candidate in referenced:
                continue
            try:
                if not candidate.is_symlink() and candidate.is_file():
                    candidate.unlink()
            except OSError:
                logger.warning("Could not clean orphan replacement stage '%s'", candidate, exc_info=True)
    return recovered
