from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from jinja2.exceptions import TemplateError
from sqlalchemy.orm import Session

from backend.api.models.local_media_profile_preview import (
    LocalMediaProfileOutputPreview,
    LocalMediaProfilePreviewRequest,
    LocalMediaProfilePreviewResult,
    LocalMediaProfileShowPreview,
)
from backend.app import db_session
from backend.db.models import Episode, Movie, MovieExtra
from backend.services.show_assets import get_show_asset_root_preview
from backend.utils.output_template import (
    _finish_output_path,
    episode_output_template_values,
    movie_output_template_values,
    output_template_fields,
)
from config import get_settings

from .output_template import (
    _EXAMPLE_MOVIE_VALUES,
    _EXAMPLE_SHOW_VALUES,
    get_output_template_preview,
)

router = APIRouter()


def _example_values(session: Session, body: LocalMediaProfilePreviewRequest) -> dict[str, str]:
    """Resolve the selected source metadata, then overlay even explicitly empty edits."""
    source_id = body.source_id
    if source_id is None or source_id == f"example:{body.type}":
        original = _EXAMPLE_SHOW_VALUES if body.type == "show" else _EXAMPLE_MOVIE_VALUES
    else:
        kind, separator, identifier = source_id.partition(":")
        models = {"episode": Episode} if body.type == "show" else {"movie": Movie, "movie-extra": MovieExtra}
        if not separator or kind not in models or not identifier.isascii() or not identifier.isdigit() or int(identifier) <= 0:
            raise ValueError("Select an example that belongs to this Local Media Profile type.")
        source = session.get(models[kind], int(identifier))
        if source is None:
            raise ValueError("The selected example no longer exists. Select another example.")
        if kind == "episode":
            original = episode_output_template_values(source)
        elif kind == "movie-extra":
            original = movie_output_template_values(source.movie, source)
        else:
            original = movie_output_template_values(source)
    return {**original, **body.values}


def get_local_media_profile_preview(
    session: Session, body: LocalMediaProfilePreviewRequest,
) -> LocalMediaProfilePreviewResult:
    """Return one read-only snapshot, including independent path diagnostics.

    Render errors are expected while typing. A bad filename does not suppress an
    otherwise resolvable show folder, and an ambiguous folder does not suppress
    a valid episode path. Both consumers receive exactly the same example values.
    """
    result = LocalMediaProfilePreviewResult(output=LocalMediaProfileOutputPreview())
    if body.type == "show":
        result.show_root = LocalMediaProfileShowPreview(
            system_enabled=get_settings().download_settings.download_show_assets,
        )
    try:
        values = _example_values(session, body)
    except ValueError as exc:
        result.output.error = str(exc)
        if result.show_root is not None:
            result.show_root.reason = str(exc)
        return result

    draft = body.model_copy(update={"values": values})
    try:
        # Keep test-value controls available even when rendering has an error.
        result.output.used_variables = sorted(output_template_fields(draft.output_template))
        rendered = get_output_template_preview(session, draft)
        result.output = LocalMediaProfileOutputPreview.model_validate(rendered)
        # Use the same concrete filesystem root and filename policy as show art,
        # rather than mixing a logical /downloads path with a real show path.
        result.output.output_path = str(_finish_output_path(
            rendered.output_path, extension=Path(rendered.output_path).suffix,
        ))
    except (TemplateError, ValueError, TypeError, ArithmeticError) as exc:
        result.output.output_path = None
        result.output.error = str(exc)

    if result.show_root is not None:
        try:
            result.show_root = LocalMediaProfileShowPreview.model_validate(get_show_asset_root_preview(
                session, source_id=draft.source_id, output_template=draft.output_template,
                local_media_profile_id=draft.local_media_profile_id, values_overrides=values,
            ))
        except (TemplateError, ValueError, TypeError, ArithmeticError) as exc:
            result.show_root.reason = str(exc)
            result.show_root.show_title = values.get("show_title")
    return result


@router.post("/preview", response_model=LocalMediaProfilePreviewResult)
def local_media_profile_preview(body: LocalMediaProfilePreviewRequest):
    """Preview an entire unsaved Local Media Profile without modifying the library."""
    with db_session() as session:
        with session.no_autoflush:
            return get_local_media_profile_preview(session, body)
