"""Non-destructive publication of re-downloaded media.

A replacement is published and committed under a unique name first. Only then
may its bytes be linked/copied beside the old file and atomically renamed over
the original path. The already-committed unique path stays valid throughout the
optional filename switch, including on database or filesystem failure.
"""
from __future__ import annotations

import logging
import os
import shutil
from contextlib import ExitStack
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from dailywire_downloader.hls_bundle import hls_asset_marker, hls_asset_root
from dailywire_downloader.storage.identity import ArtifactIdentity, inspect_artifact

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OwnedFile:
    path: Path
    identity: ArtifactIdentity


@dataclass(frozen=True)
class PreviousDownload:
    media: OwnedFile
    assets: tuple[OwnedFile, ...]


def _matches(file: OwnedFile) -> bool:
    try:
        identity = inspect_artifact(file.path)
    except (OSError, ValueError):
        return False
    return (
        identity.size_bytes == file.identity.size_bytes
        and identity.fingerprint == file.identity.fingerprint
    )


def capture_previous_download(
    media_path: str,
    *,
    size_bytes: int | None,
    fingerprint: str | None,
    assets: tuple[tuple[str, int | None, str | None], ...],
) -> PreviousDownload | None:
    """Claim only files whose content still matches the database's ownership facts."""
    path = Path(media_path)
    if path.suffix == ".ext" or size_bytes is None or not fingerprint:
        return None
    try:
        media = OwnedFile(path, inspect_artifact(path))
    except (OSError, ValueError):
        return None
    if media.identity.size_bytes != size_bytes or media.identity.fingerprint != fingerprint:
        return None

    sidecars = []
    for asset_path, asset_size, asset_fingerprint in assets:
        if asset_size is None or not asset_fingerprint:
            continue
        try:
            asset = OwnedFile(Path(asset_path), inspect_artifact(asset_path))
        except (OSError, ValueError):
            continue
        if asset.identity.size_bytes == asset_size and asset.identity.fingerprint == asset_fingerprint:
            sidecars.append(asset)
    return PreviousDownload(media, tuple(sidecars))


def _stage_sibling(source: Path, destination: Path) -> Path:
    """Create a complete link (or copy) beside the destination before renaming."""
    staged = destination.parent / f".wireloft-replace-{uuid4().hex}.part"
    try:
        try:
            os.link(source, staged)
        except OSError:
            shutil.copyfile(source, staged)
        if not _matches(OwnedFile(staged, inspect_artifact(source))):
            raise OSError(f"Staged replacement changed while copying: {source}")
        return staged
    except BaseException:
        staged.unlink(missing_ok=True)
        raise


def restore_original_filename(
    new_media_path: str,
    new_asset_paths: tuple[str, ...],
    *,
    previous: PreviousDownload,
    requested_destination: str,
) -> tuple[str, tuple[str, ...]] | None:
    """Best-effort path normalization after the new artifact has been committed.

    The database already points to the fully published new file. Every new source
    stays in place until a *second* database commit points to the normalized
    filenames, so even an interrupted rename never leaves a missing download.
    Do not rename local HLS bundles: their companion asset directory must remain
    coupled to the master playlist while clients are reading it.
    """
    from dailywire_downloader.storage.temporary import _claim_publication_lock

    old = previous.media
    new = Path(new_media_path)
    if old.path != Path(requested_destination) or old.path == new or new.suffix.lower() == ".m3u8":
        return None

    destinations: list[Path] = []
    for path in new_asset_paths:
        source = Path(path)
        if not source.name.startswith(new.stem):
            return None
        destinations.append(old.path.with_name(old.path.stem + source.name[len(new.stem):]))

    moves = list(zip((Path(path) for path in new_asset_paths), destinations, strict=True))
    moves.append((new, old.path))
    previous_assets = {item.path: item for item in previous.assets}

    # A sidecar that was not recorded as ours must not be overwritten. All
    # candidate names must remain separately usable after the rename.
    staged: list[tuple[Path, Path]] = []
    try:
        with ExitStack() as stack:
            for destination in sorted({target for _, target in moves}, key=str):
                lock = _claim_publication_lock(destination)
                if lock is None:
                    return None
                stack.callback(lock.release)

            if not _matches(old):
                return None
            for source, destination in moves:
                if not source.is_file():
                    return None
                if destination == old.path:
                    continue
                existing = previous_assets.get(destination)
                if existing is None:
                    if destination.exists():
                        return None
                elif not _matches(existing):
                    return None

            for source, destination in moves:
                staged.append((_stage_sibling(source, destination), destination))

            # These are same-filesystem renames of *completed* files. Publish
            # auxiliary files first, keeping the original media until last.
            for source, destination in staged:
                os.replace(source, destination)
            staged.clear()
            return str(old.path), tuple(str(path) for path in destinations)
    except (OSError, ValueError):
        logger.warning("Could not restore the original filename for '%s'; retaining the complete replacement at '%s'", old.path, new, exc_info=True)
        return None
    finally:
        for source, _ in staged:
            source.unlink(missing_ok=True)


def retire_superseded_files(
    previous: PreviousDownload,
    *,
    retained_paths: frozenset[str],
) -> None:
    """Remove old/duplicate files only after their replacement is committed.

    Recheck content identity just before unlinking. An external rename, edit, or
    another download must not turn this post-commit cleanup into data loss.
    """
    media = previous.media
    if str(media.path) not in retained_paths:
        # When another writer has changed the old media, its former sidecars
        # must be left alone too: we no longer own that logical file group.
        if not _matches(media):
            return
        try:
            media.path.unlink()
            if media.path.suffix.lower() == ".m3u8" and hls_asset_marker(media.path).is_file():
                shutil.rmtree(hls_asset_root(media.path))
        except OSError:
            logger.warning("Could not remove superseded media '%s'", media.path, exc_info=True)
    for asset in previous.assets:
        if str(asset.path) not in retained_paths and _matches(asset):
            try:
                asset.path.unlink()
            except OSError:
                logger.warning("Could not remove superseded sidecar '%s'", asset.path, exc_info=True)
