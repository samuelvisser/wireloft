from fastapi import APIRouter, HTTPException, Query
from jinja2.exceptions import TemplateAssertionError

from backend.api.models.local_media_profile import (
    LocalMediaProfileTemplatePreview,
    LocalMediaProfileTemplatePreviewResult,
    LocalMediaProfileTemplateSourcePage,
    LocalMediaProfileTemplateVariable,
)
from backend.api.models.local_media_profile_view import LocalMediaProfileAPIRead
from backend.app import db_session
from backend.types.local_media_profile_types import (
    LocalMediaProfileType,
    ShowLocalMediaProfileScope,
)

from .output_template import (
    get_output_template_preview,
    get_output_template_source_page,
    get_output_template_variables,
)
from .service import get_local_media_profile, get_local_media_profiles_list

router = APIRouter(prefix="/local-media-profiles", tags=["Media Profiles (base)"])


@router.get("", response_model=list[LocalMediaProfileAPIRead])
def local_media_profiles_list():
    """List Local Media Profiles of every type."""
    with db_session() as s:
        return get_local_media_profiles_list(s)


@router.get("/template/variables", response_model=list[LocalMediaProfileTemplateVariable])
def local_media_profile_template_variables(
    type: LocalMediaProfileType = Query(...),
):
    """Return custom variables available to one output-template type."""
    with db_session() as s:
        try:
            return get_output_template_variables(s, type)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/template/sources", response_model=LocalMediaProfileTemplateSourcePage)
def local_media_profile_template_sources(
    type: LocalMediaProfileType = Query(...),
    show_scope: ShowLocalMediaProfileScope = Query(ShowLocalMediaProfileScope.BOTH),
    search: str | None = Query(None, max_length=200),
    offset: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=100),
):
    """Search applicable media items for testing an output path template."""
    with db_session() as s:
        try:
            return get_output_template_source_page(
                s,
                type,
                show_scope,
                search=search,
                offset=offset,
                limit=limit,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/template/preview", response_model=LocalMediaProfileTemplatePreviewResult)
def local_media_profile_template_preview(body: LocalMediaProfileTemplatePreview):
    """Render an unsaved output path template against editable example values."""
    try:
        return get_output_template_preview(body)
    except (ValueError, TemplateAssertionError) as exc:
        message = exc.message if isinstance(exc, TemplateAssertionError) else str(exc)
        raise HTTPException(
            status_code=422,
            detail=[{
                "loc": ["body", "outputTemplate"],
                "msg": message,
                "type": "value_error",
            }],
        ) from exc


@router.get("/{local_media_profile_slug}", response_model=LocalMediaProfileAPIRead)
def local_media_profiles_detail(local_media_profile_slug: str):
    """Retrieve a Local Media Profile of any type."""
    with db_session() as s:
        return get_local_media_profile(s, local_media_profile_slug)
