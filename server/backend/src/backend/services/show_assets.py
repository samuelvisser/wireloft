"""Shared show-directory resolution and artwork reconciliation requests."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from os.path import normcase
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from backend.db.models import DownloadProfileBase, Episode, EpisodeMediaDownload, Show, ShowLocalMediaProfile
from backend.db.models.ShowLocalAsset import ShowLocalAsset
from backend.utils.custom_metadata import custom_metadata_template_values, get_custom_metadata
from backend.utils.output_template import (
    SHOW_OUTPUT_TEMPLATE_FIELDS, SHOW_OUTPUT_TEMPLATE_METADATA_SCOPES,
    _sanitize_emitted_output_value, output_template_fields, sanitize_path_component,
    validate_output_template_path_requirements,
)
from backend.utils.output_template_jinja import create_output_template_environment
from backend.utils.show_media_directory import ShowMediaDirectory, infer_show_media_directory
from config import get_settings

if TYPE_CHECKING:
    from dailywire_api.records import DwShowRecord

SHOW_ASSETS_REQUESTED = "show_assets.reconcile_requested"


@dataclass(frozen=True)
class ShowAssetRootPreview:
    path: str | None
    reason: str | None
    show_title: str | None
    system_enabled: bool


def show_assets_enabled(profile: ShowLocalMediaProfile) -> bool:
    override = profile.download_show_assets
    return get_settings().download_settings.download_show_assets if override is None else override


def managed_show_profile_pairs(session: Session) -> set[tuple[int, int]]:
    """Include manual downloads as well as Download Profile assignments."""
    pairs = set(session.execute(select(DownloadProfileBase.show_id, DownloadProfileBase.local_media_profile_id)).all())
    pairs.update(session.execute(
        select(Episode.show_id, EpisodeMediaDownload.local_media_profile_id)
        .join(EpisodeMediaDownload, EpisodeMediaDownload.media_item_id == Episode.id)
    ).all())
    return {(show_id, profile_id) for show_id, profile_id in pairs if show_id is not None and profile_id is not None}


def resolve_show_media_directory(show: Show, output_template: str) -> ShowMediaDirectory:
    """Resolve against real show metadata, including the production path policy.

    Episode values need not be invented: the semantic resolver marks them as
    variable and explores their structural branches without assigning indexes.
    """
    validate_output_template_path_requirements(
        output_template,
        allowed_fields=SHOW_OUTPUT_TEMPLATE_FIELDS,
        allowed_metadata_scopes=SHOW_OUTPUT_TEMPLATE_METADATA_SCOPES,
    )
    values = {field: "" for field in SHOW_OUTPUT_TEMPLATE_FIELDS | output_template_fields(output_template)}
    values.update(show=show.slug, show_title=show.title)
    values.update(custom_metadata_template_values("show", get_custom_metadata(show)))
    environment = create_output_template_environment(custom_index_resolver=lambda _key: "")
    environment.finalize = _sanitize_emitted_output_value
    settings = get_settings().download_settings
    names = tuple(
        str(value) for season in show.seasons
        for value in (season.slug, season.name, season.index, season.season_number)
        if value is not None
    )
    resolution = infer_show_media_directory(
        output_template, values, environment=environment,
        sanitize_component=lambda part: sanitize_path_component(part, mode=settings.filename_restriction_mode),
        season_names=names,
    )
    if resolution.path is None:
        return resolution
    base = Path(settings.download_root).resolve()
    destination = (base / resolution.path.removeprefix("/downloads/")).resolve()
    if destination == base or not destination.is_relative_to(base):
        return ShowMediaDirectory(None, "The resolved show root is outside the download root or is the download root itself.")
    return ShowMediaDirectory(str(destination))


def show_profile_roots(
    session: Session, *, draft_profile_id: int | None = None, draft_template: str | None = None,
) -> dict[tuple[int, int], ShowMediaDirectory]:
    pairs = managed_show_profile_pairs(session)
    if not pairs:
        return {}
    profiles = {profile.id: profile for profile in session.scalars(
        select(ShowLocalMediaProfile).where(ShowLocalMediaProfile.id.in_({profile_id for _, profile_id in pairs}))
    )}
    shows = {show.id: show for show in session.scalars(
        select(Show).where(Show.id.in_({show_id for show_id, _ in pairs}))
        .options(selectinload(Show.seasons), selectinload(Show.meta_items))
    )}
    roots = {}
    for show_id, profile_id in sorted(pairs):
        show, profile = shows.get(show_id), profiles.get(profile_id)
        if show is None or profile is None:
            continue
        template = draft_template if profile_id == draft_profile_id and draft_template is not None else profile.output_template
        try:
            roots[show_id, profile_id] = resolve_show_media_directory(show, template)
        except ValueError as exc:
            roots[show_id, profile_id] = ShowMediaDirectory(None, str(exc))
    return roots


def shared_root_conflict(roots: dict[tuple[int, int], ShowMediaDirectory], show_id: int, path: str) -> bool:
    # Compare normalized filesystem paths, not unsanitized show titles.
    for (other_show, _), root in roots.items():
        if other_show == show_id or root.path is None:
            continue
        if normcase(root.path) == normcase(path):
            return True
        # Case-insensitive network mounts can exist on case-sensitive hosts.
        # Avoid filesystem round trips unless the names differ only in case.
        if root.path.casefold() == path.casefold():
            try:
                if Path(root.path).samefile(path):
                    return True
            except OSError:
                pass
    return False


def get_show_asset_root_preview(
    session: Session, *, source_id: str | None, output_template: str, local_media_profile_id: int | None,
) -> ShowAssetRootPreview:
    enabled = get_settings().download_settings.download_show_assets
    if not source_id or not source_id.startswith("episode:") or not source_id[8:].isdigit():
        return ShowAssetRootPreview(None, "Select an indexed episode in the Jinja editor to resolve its show's root.", None, enabled)
    episode = session.get(Episode, int(source_id[8:]))
    if episode is None:
        return ShowAssetRootPreview(None, "The selected episode no longer exists.", None, enabled)
    show = episode.show
    result = resolve_show_media_directory(show, output_template)
    if result.path:
        roots = show_profile_roots(session, draft_profile_id=local_media_profile_id, draft_template=output_template)
        if shared_root_conflict(roots, show.id, result.path):
            result = ShowMediaDirectory(None, "This directory is also used by another show. Shared artwork would collide.")
    return ShowAssetRootPreview(result.path, result.reason, show.title, enabled)


def show_asset_sources(show: Show) -> tuple[tuple[str, str], ...]:
    choices = {
        "poster": (show.thumbnail_portrait_path, show.thumbnail_square_path),
        "fanart": (show.background_image_path, show.thumbnail_landscape_path),
        "square": (show.thumbnail_square_path,),
    }
    return tuple(
        (kind, url) for kind, candidates in choices.items()
        if (url := next((value for value in candidates if isinstance(value, str) and value.startswith(("https://", "http://"))), None))
    )


def request_show_asset_reconciliation(session: Session, show_id: int = 0) -> None:
    from task_manager.events.transactional import queue_event
    queue_event(session, SHOW_ASSETS_REQUESTED, {"resource_id": show_id})


def request_profile_show_assets(session: Session, profile_id: int) -> None:
    pairs = managed_show_profile_pairs(session)
    pairs.update(session.execute(select(ShowLocalAsset.show_id, ShowLocalAsset.local_media_profile_id)).all())
    for show_id in sorted({show_id for show_id, candidate in pairs if candidate == profile_id}):
        request_show_asset_reconciliation(session, show_id)


def update_show_artwork_metadata(show: Show, source: "DwShowRecord") -> None:
    """Reuse the already fetched show page; absent variants keep their known URL."""
    for field in (
        "thumbnail_portrait_path", "thumbnail_landscape_path", "thumbnail_square_path",
        "background_image_path", "logo_image_path",
    ):
        value = getattr(source, field, None)
        if value:
            setattr(show, field, value)
