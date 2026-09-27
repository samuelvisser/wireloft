from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
import tempfile
from typing import Callable

from dailywire_downloader import DownloadCancelled

from sqlalchemy import select

from backend.db.models import DownloadProfileBase, Episode, EpisodeMediaDownload, Show, ShowLocalMediaProfile
from backend.db.models.ShowLocalAsset import ShowLocalAsset
from backend.services.show_assets import (
    managed_show_profile_pairs, resolve_show_media_directory, shared_root_conflict,
    show_asset_sources, show_assets_enabled, show_profile_roots,
)
from backend.utils.show_asset_files import (
    ArtworkConflict, asset_file_hash, asset_file_lock, download_show_asset_jpeg,
    publish_show_asset, safe_asset_path,
)
from config import get_settings
from controller.db_utils import db_session
from task_manager.tasks.helpers.progress import update_progress

logger = logging.getLogger(__name__)
_REFRESH_AFTER = timedelta(days=1)


@dataclass(frozen=True)
class AssetPlan:
    show_id: int
    profile_id: int
    kind: str
    url: str
    target: Path
    download_root: Path
    output_template: str


def _current(session, plan: AssetPlan) -> bool:
    profile = session.get(ShowLocalMediaProfile, plan.profile_id)
    show = session.get(Show, plan.show_id)
    if profile is None or show is None or not show_assets_enabled(profile):
        return False
    if profile.output_template != plan.output_template:
        return False
    if (plan.show_id, plan.profile_id) not in managed_show_profile_pairs(session):
        return False
    if Path(get_settings().download_settings.download_root).resolve() != plan.download_root:
        return False
    return (
        resolve_show_media_directory(show, profile.output_template).path == str(plan.target.parent)
        and dict(show_asset_sources(show)).get(plan.kind) == plan.url
    )


def _owned_file(session, plan):
    safe_asset_path(plan.download_root, plan.target)
    rows = list(session.scalars(select(ShowLocalAsset).where(ShowLocalAsset.file_path == str(plan.target))))
    if any(row.show_id != plan.show_id for row in rows):
        raise ArtworkConflict(f"Another show owns artwork at {plan.target}")
    for suffix in (".png", ".jpeg", ".webp"):
        alternate = plan.target.with_suffix(suffix)
        if alternate.exists() or alternate.is_symlink():
            raise ArtworkConflict(f"Existing alternate-format artwork was left untouched: {alternate}")
    digest = asset_file_hash(plan.target)
    if digest is not None and not any(digest in (row.content_hash, row.pending_hash) for row in rows):
        raise ArtworkConflict(f"User-supplied or edited artwork was left untouched: {plan.target}")
    return rows, digest


def _owner(session, rows, plan):
    owner = next((row for row in rows if row.local_media_profile_id == plan.profile_id and row.asset_type == plan.kind), None)
    if owner is None:
        owner = ShowLocalAsset(show_id=plan.show_id, local_media_profile_id=plan.profile_id, asset_type=plan.kind, file_path=str(plan.target))
        session.add(owner)
        rows.append(owner)
    return owner


def _refresh_asset(plan: AssetPlan, check_cancelled: Callable[[], None]) -> bool:
    check_cancelled()
    now = datetime.now(timezone.utc)
    with asset_file_lock(plan.download_root, plan.target):
        with db_session() as session:
            if not _current(session, plan):
                return False
            rows, digest = _owned_file(session, plan)
            fresh = next((row for row in rows if digest is not None and row.content_hash == digest
                          and row.pending_hash is None and row.source_url == plan.url and row.checked_at is not None
                          and now - row.checked_at < _REFRESH_AFTER), None)
            if fresh is not None:
                owner = _owner(session, rows, plan)
                owner.content_hash, owner.source_url, owner.checked_at = digest, plan.url, fresh.checked_at
                owner.pending_hash = None
                session.commit()
                return True

    # No database transaction or filesystem publication lock spans HTTP/FFmpeg.
    with tempfile.TemporaryDirectory(prefix="wireloft-show-assets-") as temporary:
        prepared = download_show_asset_jpeg(
            plan.url, Path(temporary), ffmpeg_path=get_settings().download_settings.ffmpeg_path,
            check_cancelled=check_cancelled,
        )
        new_hash = asset_file_hash(prepared)
        if new_hash is None:
            raise ValueError("Prepared show artwork disappeared before publication")
        check_cancelled()
        with asset_file_lock(plan.download_root, plan.target):
            with db_session() as session:
                if not _current(session, plan):
                    return False
                if shared_root_conflict(show_profile_roots(session), plan.show_id, str(plan.target.parent)):
                    raise ArtworkConflict("The show directory became shared by another show")
                rows, previous_hash = _owned_file(session, plan)
                _owner(session, rows, plan)
                for row in rows:
                    row.pending_hash = new_hash
                # A retry recognizes the new bytes after a crash before final commit.
                session.commit()
                if new_hash != previous_hash:
                    publish_show_asset(
                        prepared, plan.target, download_root=plan.download_root,
                        expected_hash=previous_hash, check_cancelled=check_cancelled,
                    )
                for row in rows:
                    row.content_hash = new_hash
                    row.pending_hash = None
                    row.source_url = plan.url
                    row.checked_at = now
                session.commit()
    return True


def _cleanup_old_roots(
    show_id: int, profile_id: int, current_root: Path, download_root: Path,
    check_cancelled: Callable[[], None],
) -> None:
    with db_session() as session:
        obsolete = [(row.id, Path(row.file_path)) for row in session.scalars(select(ShowLocalAsset).where(
            ShowLocalAsset.show_id == show_id, ShowLocalAsset.local_media_profile_id == profile_id,
        )) if Path(row.file_path).parent != current_root]
        media_paths = [Path(path).resolve() for path in session.scalars(
            select(EpisodeMediaDownload.file_path).join(Episode, Episode.id == EpisodeMediaDownload.media_item_id)
            .where(Episode.show_id == show_id, EpisodeMediaDownload.local_media_profile_id == profile_id)
        ) if path]
    for record_id, path in obsolete:
        check_cancelled()
        # A template may change without the user requesting existing media renames.
        # A missing file may simply await file-watcher rename reconciliation.
        if any(media.is_relative_to(path.parent) and not media.is_relative_to(current_root) for media in media_paths):
            continue
        try:
            with asset_file_lock(download_root, path):
                with db_session() as session:
                    row = session.get(ShowLocalAsset, record_id)
                    profile = session.get(ShowLocalMediaProfile, profile_id)
                    show = session.get(Show, show_id)
                    if row is None or profile is None or show is None or not show_assets_enabled(profile):
                        continue
                    if (show_id, profile_id) not in managed_show_profile_pairs(session):
                        continue
                    if resolve_show_media_directory(show, profile.output_template).path != str(current_root):
                        continue
                    replacement = session.scalar(select(ShowLocalAsset).where(
                        ShowLocalAsset.show_id == show_id,
                        ShowLocalAsset.local_media_profile_id == profile_id,
                        ShowLocalAsset.asset_type == row.asset_type,
                        ShowLocalAsset.file_path == str(current_root / f"{row.asset_type}.jpg"),
                    ))
                    if replacement is None or replacement.content_hash is None:
                        continue
                    if asset_file_hash(Path(replacement.file_path)) != replacement.content_hash:
                        continue
                    shared = session.scalar(select(ShowLocalAsset.id).where(
                        ShowLocalAsset.file_path == str(path), ShowLocalAsset.id != record_id,
                    ).limit(1))
                    if shared is None:
                        digest = asset_file_hash(path)
                        if digest is not None and digest in (row.content_hash, row.pending_hash):
                            safe_asset_path(download_root, path).unlink(missing_ok=True)
                    # Modified artwork is preserved but is no longer claimed by us.
                    session.delete(row)
                    session.commit()
        except ArtworkConflict as exc:
            logger.warning("Old show artwork was left untouched: %s", exc)


def run_reconcile_show_assets(
    *, resource_id=None, resource_type=None, progress=None, check_cancelled: Callable[[], None],
) -> None:
    warnings = []
    plans = []
    cleanup = []
    download_root = Path(get_settings().download_settings.download_root).resolve()
    with db_session() as session:
        if resource_type == "download_profile" and resource_id:
            profile = session.get(DownloadProfileBase, resource_id)
            if profile is None:
                return
            show_id = profile.show_id
        else:
            show_id = resource_id or None
        check_cancelled()
        roots = show_profile_roots(session)
        indexed_show_ids = set(session.scalars(select(Episode.show_id).distinct()))
        for (current_show_id, profile_id), root in roots.items():
            if current_show_id not in indexed_show_ids:
                continue
            if show_id is not None and current_show_id != show_id:
                continue
            profile = session.get(ShowLocalMediaProfile, profile_id)
            show = session.get(Show, current_show_id)
            if profile is None or show is None or not show_assets_enabled(profile):
                continue
            if root.path is None or shared_root_conflict(roots, current_show_id, root.path):
                warnings.append(f"{show.title}: {root.reason or 'the artwork directory is shared by another show'}")
                continue
            directory = Path(root.path)
            sources = show_asset_sources(show)
            plans.extend(AssetPlan(show.id, profile_id, kind, url, directory / f"{kind}.jpg", download_root, profile.output_template)
                         for kind, url in sources)
            if sources:
                cleanup.append((show.id, profile_id, directory))

    errors = []
    failed_pairs = set()
    for index, plan in enumerate(plans):
        update_progress(progress, int(index * 90 / max(1, len(plans))), f"Reconciling show artwork ({index + 1}/{len(plans)})")
        try:
            if not _refresh_asset(plan, check_cancelled):
                failed_pairs.add((plan.show_id, plan.profile_id))
        except DownloadCancelled:
            raise
        except ArtworkConflict as exc:
            warnings.append(str(exc))
            failed_pairs.add((plan.show_id, plan.profile_id))
        except Exception as exc:
            logger.exception("Show %s artwork %s could not be refreshed", plan.show_id, plan.kind)
            errors.append(str(exc))
            failed_pairs.add((plan.show_id, plan.profile_id))
    for show_id, profile_id, directory in cleanup:
        if (show_id, profile_id) not in failed_pairs:
            _cleanup_old_roots(show_id, profile_id, directory, download_root, check_cancelled)
    for warning in warnings:
        logger.warning("Show artwork: %s", warning)
    if errors:
        raise RuntimeError(f"Could not refresh {len(errors)} show artwork file(s): {errors[0]}")
    update_progress(progress, 100, f"Reconciled show artwork; {len(warnings)} skipped or ambiguous destination(s)")
