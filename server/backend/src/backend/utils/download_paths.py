from __future__ import annotations

import os
from itertools import count
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.db.models.media_download import MediaDownloadBase
from backend.utils.output_template import resolve_episode_output_path

if TYPE_CHECKING:
    from backend.db.models import Episode


_TEMP_ARTIFACT_SUFFIXES = (".rawts.part", ".rawts", ".part")


def _normalized_path(path: str | Path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def _strip_temporary_artifact_suffix(path: Path) -> Path:
    name = path.name
    for suffix in _TEMP_ARTIFACT_SUFFIXES:
        if name.endswith(suffix):
            return path.with_name(name[:-len(suffix)])
    return path


def _collision_key(path: str | Path) -> str:
    """Compare paths by directory and filename without the media extension."""
    artifact_path = _strip_temporary_artifact_suffix(Path(path))
    return _normalized_path(artifact_path.with_suffix(""))


def _owned_artifact_paths(file_path: str | None) -> set[str]:
    if not file_path:
        return set()
    return {
        _normalized_path(file_path),
        _normalized_path(file_path + ".part"),
        _normalized_path(file_path + ".rawts"),
        _normalized_path(file_path + ".rawts.part"),
    }


def _is_rendered_path_variant(current_path: Path, rendered_path: Path) -> bool:
    if _normalized_path(current_path.parent) != _normalized_path(rendered_path.parent):
        return False

    current_stem = current_path.stem
    rendered_stem = rendered_path.stem
    if current_stem == rendered_stem:
        return True

    numbered_prefix = f"{rendered_stem}-"
    if not current_stem.startswith(numbered_prefix):
        return False
    suffix = current_stem[len(numbered_prefix):]
    return suffix.isdigit() and int(suffix) > 0


def _physical_path_collides(candidate: Path, *, ignored_paths: set[str]) -> bool:
    parent = candidate.parent
    if not parent.exists():
        return False

    candidate_key = _collision_key(candidate)
    for existing in parent.iterdir():
        if _normalized_path(existing) in ignored_paths:
            continue
        if _collision_key(existing) == candidate_key:
            return True
    return False


def _path_is_available(
    candidate: Path,
    *,
    reserved_keys: set[str],
    ignored_physical_paths: set[str],
) -> bool:
    candidate_key = _collision_key(candidate)
    return (
        candidate_key not in reserved_keys
        and not _physical_path_collides(candidate, ignored_paths=ignored_physical_paths)
    )


def resolve_unique_episode_download_path(
    session: Session,
    output_template: str,
    *,
    episode: "Episode",
    current_download: MediaDownloadBase | None = None,
) -> Path:
    """Resolve and reserve a collision-free basename for an episode download.

    MediaDownload rows are treated as reservations even while queued, and files
    already present on disk are also respected. The concrete media extension is
    deliberately ignored for collision purposes because queued rows still use
    the template's ``.ext`` marker while completed rows use extensions such as
    ``.m4a`` or ``.mp4``.
    """
    rendered_path = resolve_episode_output_path(output_template, episode=episode)

    stmt = select(MediaDownloadBase.file_path)
    if current_download is not None and current_download.id is not None:
        stmt = stmt.where(MediaDownloadBase.id != current_download.id)
    reserved_keys = {
        _collision_key(file_path)
        for file_path in session.scalars(stmt)
        if file_path
    }

    current_file_path = current_download.file_path if current_download is not None else None
    ignored_physical_paths = _owned_artifact_paths(current_file_path)

    # Keep a previously allocated suffix stable across retries and re-downloads
    # as long as the Local Media Profile still renders the same base location.
    if current_file_path:
        current_path = Path(current_file_path)
        if (
            _is_rendered_path_variant(current_path, rendered_path)
            and _path_is_available(
                current_path,
                reserved_keys=reserved_keys,
                ignored_physical_paths=ignored_physical_paths,
            )
        ):
            return current_path

    if _path_is_available(
        rendered_path,
        reserved_keys=reserved_keys,
        ignored_physical_paths=ignored_physical_paths,
    ):
        return rendered_path

    for number in count(1):
        candidate = rendered_path.with_name(
            f"{rendered_path.stem}-{number}{rendered_path.suffix}"
        )
        if _path_is_available(
            candidate,
            reserved_keys=reserved_keys,
            ignored_physical_paths=ignored_physical_paths,
        ):
            return candidate

    raise RuntimeError("Could not allocate a unique episode download path")


def replace_download_path_extension(path: str | Path, extension: str) -> Path:
    """Replace the placeholder/current media extension without changing its basename."""
    normalized_extension = extension.lstrip(".")
    if not normalized_extension:
        raise ValueError("Download extension must not be empty")
    return Path(path).with_suffix(f".{normalized_extension}")
