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
    ArtworkConflict, PreparedShowAsset, asset_file_hash, asset_file_lock,
    download_show_asset, publish_show_asset, safe_asset_path,
)
from config import get_settings
from controller.db_utils import db_session
from task_manager.tasks.helpers.progress import update_progress

logger = logging.getLogger(__name__)
_REFRESH_AFTER = timedelta(days=1)
_SUPPORTED_EXTENSIONS = (".jpg", ".jpeg", ".png", ".webp")


@dataclass(frozen=True)
class AssetPlan:
    show_id: int
    profile_id: int
    kind: str
    url: str
    directory: Path
    download_root: Path
    output_template: str
    forced_format: str | None = None


def _fallback_format() -> str:
    value = get_settings().download_settings.show_artwork_fallback_format
    return str(getattr(value, "value", value))


def _expected_output_format(row: ShowLocalAsset, plan: AssetPlan) -> str | None:
    if plan.forced_format is not None:
        return plan.forced_format
    if row.source_format in {"jpg", "png"}:
        return row.source_format
    if row.source_format == "other":
        return _fallback_format()
    return None


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
    source = next((candidate for candidate in show_asset_sources(show) if candidate.kind == plan.kind), None)
    return (
        resolve_show_media_directory(show, profile.output_template).path == str(plan.directory)
        and source is not None
        and source.url == plan.url
        and source.forced_format == plan.forced_format
    )


def _path_rows(session, path: Path) -> list[ShowLocalAsset]:
    return list(session.scalars(select(ShowLocalAsset).where(ShowLocalAsset.file_path == str(path))))


def _asset_rows(session, plan: AssetPlan) -> list[ShowLocalAsset]:
    return list(session.scalars(select(ShowLocalAsset).where(
        ShowLocalAsset.show_id == plan.show_id,
        ShowLocalAsset.asset_type == plan.kind,
    )))


def _owned_file(session, plan: AssetPlan, target: Path):
    safe_asset_path(plan.download_root, target)
    rows = _path_rows(session, target)
    if any(row.show_id != plan.show_id for row in rows):
        raise ArtworkConflict(f"Another show owns artwork at {target}")

    for suffix in _SUPPORTED_EXTENSIONS:
        alternate = target.with_suffix(suffix)
        if alternate == target or not (alternate.exists() or alternate.is_symlink()):
            continue
        alternate_rows = _path_rows(session, alternate)
        alternate_digest = asset_file_hash(alternate)
        if alternate_digest is None or not any(
            row.show_id == plan.show_id
            and alternate_digest in (row.content_hash, row.pending_hash)
            for row in alternate_rows
        ):
            raise ArtworkConflict(f"Existing alternate-format artwork was left untouched: {alternate}")

    digest = asset_file_hash(target)
    if digest is not None and not any(digest in (row.content_hash, row.pending_hash) for row in rows):
        raise ArtworkConflict(f"User-supplied or edited artwork was left untouched: {target}")
    return rows, digest


def _owner(session, rows, plan: AssetPlan, target: Path) -> ShowLocalAsset:
    owner = next((
        row for row in rows
        if row.local_media_profile_id == plan.profile_id and row.asset_type == plan.kind
    ), None)
    if owner is None:
        owner = ShowLocalAsset(
            show_id=plan.show_id,
            local_media_profile_id=plan.profile_id,
            asset_type=plan.kind,
            file_path=str(target),
        )
        session.add(owner)
        rows.append(owner)
    return owner


def _claim_fresh_asset(
    plan: AssetPlan,
    now: datetime,
    check_cancelled: Callable[[], None],
) -> tuple[bool, Path | None]:
    with db_session() as session:
        if not _current(session, plan):
            return False, None
        candidates = [
            Path(row.file_path)
            for row in _asset_rows(session, plan)
            if Path(row.file_path).parent == plan.directory
            and row.source_url == plan.url
            and row.pending_hash is None
            and row.checked_at is not None
            and now - row.checked_at < _REFRESH_AFTER
            and _expected_output_format(row, plan) is not None
            and Path(row.file_path).suffix.lower() == f".{_expected_output_format(row, plan)}"
        ]

    for target in dict.fromkeys(candidates):
        check_cancelled()
        with asset_file_lock(plan.download_root, target):
            with db_session() as session:
                if not _current(session, plan):
                    return False, None
                rows = _path_rows(session, target)
                if any(row.show_id != plan.show_id for row in rows):
                    raise ArtworkConflict(f"Another show owns artwork at {target}")
                digest = asset_file_hash(target)
                owned_by_profile = next((
                    row for row in rows
                    if row.show_id == plan.show_id
                    and row.local_media_profile_id == plan.profile_id
                    and row.asset_type == plan.kind
                ), None)
                if owned_by_profile is not None and digest not in (
                    owned_by_profile.content_hash,
                    owned_by_profile.pending_hash,
                ):
                    raise ArtworkConflict(f"User-supplied or edited artwork was left untouched: {target}")
                fresh = next((
                    row for row in rows
                    if row.show_id == plan.show_id
                    and row.asset_type == plan.kind
                    and digest is not None
                    and row.content_hash == digest
                    and row.pending_hash is None
                    and row.source_url == plan.url
                    and row.checked_at is not None
                    and now - row.checked_at < _REFRESH_AFTER
                    and _expected_output_format(row, plan) is not None
                    and target.suffix.lower() == f".{_expected_output_format(row, plan)}"
                ), None)
                if fresh is None:
                    continue
                owner = _owner(session, rows, plan, target)
                owner.content_hash = digest
                owner.pending_hash = None
                owner.source_url = plan.url
                owner.source_format = fresh.source_format
                owner.checked_at = fresh.checked_at
                session.commit()
                return True, target
    return True, None


def _cleanup_obsolete_variants(
    plan: AssetPlan,
    current_target: Path,
    check_cancelled: Callable[[], None],
) -> None:
    with db_session() as session:
        obsolete = [
            (row.id, Path(row.file_path))
            for row in session.scalars(select(ShowLocalAsset).where(
                ShowLocalAsset.show_id == plan.show_id,
                ShowLocalAsset.local_media_profile_id == plan.profile_id,
                ShowLocalAsset.asset_type == plan.kind,
            ))
            if Path(row.file_path).parent == plan.directory and Path(row.file_path) != current_target
        ]

    for record_id, path in obsolete:
        check_cancelled()
        try:
            with asset_file_lock(plan.download_root, path):
                with db_session() as session:
                    row = session.get(ShowLocalAsset, record_id)
                    if row is None or not _current(session, plan):
                        continue
                    replacement = session.scalar(select(ShowLocalAsset).where(
                        ShowLocalAsset.show_id == plan.show_id,
                        ShowLocalAsset.local_media_profile_id == plan.profile_id,
                        ShowLocalAsset.asset_type == plan.kind,
                        ShowLocalAsset.file_path == str(current_target),
                    ))
                    if (
                        replacement is None
                        or replacement.content_hash is None
                        or asset_file_hash(current_target) != replacement.content_hash
                    ):
                        continue
                    shared = session.scalar(select(ShowLocalAsset.id).where(
                        ShowLocalAsset.file_path == str(path),
                        ShowLocalAsset.id != record_id,
                    ).limit(1))
                    if shared is None:
                        digest = asset_file_hash(path)
                        if digest is not None and digest in (row.content_hash, row.pending_hash):
                            safe_asset_path(plan.download_root, path).unlink(missing_ok=True)
                    session.delete(row)
                    session.commit()
        except ArtworkConflict as exc:
            logger.warning("Old show artwork variant was left untouched: %s", exc)


def _refresh_asset(plan: AssetPlan, check_cancelled: Callable[[], None]) -> bool:
    check_cancelled()
    now = datetime.now(timezone.utc)
    current, fresh_target = _claim_fresh_asset(plan, now, check_cancelled)
    if not current:
        return False
    if fresh_target is not None:
        _cleanup_obsolete_variants(plan, fresh_target, check_cancelled)
        return True

    with tempfile.TemporaryDirectory(prefix="wireloft-show-assets-") as temporary:
        settings = get_settings().download_settings
        prepared: PreparedShowAsset = download_show_asset(
            plan.url,
            Path(temporary),
            ffmpeg_path=settings.ffmpeg_path,
            fallback_format=settings.show_artwork_fallback_format,
            forced_format=plan.forced_format,
            check_cancelled=check_cancelled,
        )
        target = plan.directory / f"{plan.kind}.{prepared.output_format}"
        new_hash = asset_file_hash(prepared.path)
        if new_hash is None:
            raise ValueError("Prepared show artwork disappeared before publication")
        check_cancelled()
        with asset_file_lock(plan.download_root, target):
            with db_session() as session:
                if not _current(session, plan):
                    return False
                if shared_root_conflict(show_profile_roots(session), plan.show_id, str(plan.directory)):
                    raise ArtworkConflict("The show directory became shared by another show")
                rows, previous_hash = _owned_file(session, plan, target)
                _owner(session, rows, plan, target)
                for row in rows:
                    row.pending_hash = new_hash
                session.commit()
                if new_hash != previous_hash:
                    publish_show_asset(
                        prepared.path,
                        target,
                        download_root=plan.download_root,
                        expected_hash=previous_hash,
                        check_cancelled=check_cancelled,
                    )
                for row in rows:
                    row.content_hash = new_hash
                    row.pending_hash = None
                    row.source_url = plan.url
                    row.source_format = prepared.source_format
                    row.checked_at = now
                session.commit()

    _cleanup_obsolete_variants(plan, target, check_cancelled)
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
                    replacements = list(session.scalars(select(ShowLocalAsset).where(
                        ShowLocalAsset.show_id == show_id,
                        ShowLocalAsset.local_media_profile_id == profile_id,
                        ShowLocalAsset.asset_type == row.asset_type,
                    )))
                    replacement = next((
                        candidate for candidate in replacements
                        if Path(candidate.file_path).parent == current_root
                        and candidate.content_hash is not None
                    ), None)
                    if replacement is None:
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
                warnings.append(
                    f"{show.title} via Local Media Profile '{profile.name}': "
                    f"{root.reason or 'the artwork directory is shared by another show'}"
                )
                continue
            directory = Path(root.path)
            sources = show_asset_sources(show)
            plans.extend(
                AssetPlan(
                    show.id,
                    profile_id,
                    source.kind,
                    source.url,
                    directory,
                    download_root,
                    profile.output_template,
                    source.forced_format,
                )
                for source in sources
            )
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
