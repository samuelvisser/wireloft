from fastapi import APIRouter, HTTPException, Query

from backend.api.models.local_media_profile import (
    LocalMediaProfileTemplateSource,
    LocalMediaProfileTemplateSourcePage,
    LocalMediaProfileTemplateVariable,
)
from backend.api.models.local_media_profile_view import (
    LocalMediaProfileAPIRead,
    LocalMediaProfileViewAPIRead,
)
from backend.api.models.operations import (
    LocalMediaProfileDeleteDownloadsOperationAccepted,
    LocalMediaProfileFileRenameOperationAccepted,
    LocalMediaProfileRedownloadOperationAccepted,
)
from backend.app import db_session
from backend.types.local_media_profile_types import (
    LocalMediaProfileType,
    ShowLocalMediaProfileScope,
)

from .output_template import (
    get_output_template_source_page,
    get_random_show_template_source,
    get_output_template_variables,
)
from .file_rename import request_local_media_profile_file_rename
from .maintenance import (
    request_local_media_profile_download_delete,
    request_local_media_profile_redownload,
)
from .advisory import router as advisory_router
from .preview import router as preview_router
from .service import (
    get_local_media_profile,
    get_local_media_profile_view,
    get_local_media_profile_views_list,
    get_local_media_profiles_list,
)

router = APIRouter(prefix="/local-media-profiles", tags=["Media Profiles (base)"])
router.include_router(preview_router)
router.include_router(advisory_router)


@router.get("", response_model=list[LocalMediaProfileAPIRead])
def local_media_profiles_list():
    """List Local Media Profiles of every type."""
    with db_session() as s:
        return get_local_media_profiles_list(s)


@router.get("/as-view", response_model=list[LocalMediaProfileViewAPIRead])
def local_media_profiles_view_list():
    """List Local Media Profiles together with management statistics."""
    with db_session() as s:
        return get_local_media_profile_views_list(s)


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
    anchor_source_id: str | None = Query(None, max_length=100),
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
                anchor_source_id=anchor_source_id,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/template/sources/random-show-episode",
    response_model=LocalMediaProfileTemplateSource | None,
)
def local_media_profile_random_show_template_source(
    show_scope: ShowLocalMediaProfileScope = Query(ShowLocalMediaProfileScope.BOTH),
):
    """Choose a fresh initial episode without weighting Shows by episode count."""
    with db_session() as s:
        return get_random_show_template_source(s, show_scope)


@router.get(
    "/{local_media_profile_slug}/view",
    response_model=LocalMediaProfileViewAPIRead,
)
def local_media_profiles_view(local_media_profile_slug: str):
    """Retrieve one Local Media Profile together with management statistics."""
    with db_session() as s:
        return get_local_media_profile_view(s, local_media_profile_slug)


@router.post(
    "/{local_media_profile_slug}/rename-files",
    response_model=LocalMediaProfileFileRenameOperationAccepted,
    status_code=202,
)
def local_media_profiles_rename_files(local_media_profile_slug: str):
    with db_session() as s:
        try:
            result = request_local_media_profile_file_rename(
                s,
                local_media_profile_slug,
            )
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.post(
    "/{local_media_profile_slug}/delete-downloads",
    response_model=LocalMediaProfileDeleteDownloadsOperationAccepted,
    status_code=202,
)
def local_media_profiles_delete_downloads(local_media_profile_slug: str):
    with db_session() as s:
        try:
            result = request_local_media_profile_download_delete(
                s,
                local_media_profile_slug,
            )
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.post(
    "/{local_media_profile_slug}/redownload-media",
    response_model=LocalMediaProfileRedownloadOperationAccepted,
    status_code=202,
)
def local_media_profiles_redownload_media(local_media_profile_slug: str):
    with db_session() as s:
        try:
            result = request_local_media_profile_redownload(
                s,
                local_media_profile_slug,
            )
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.get("/{local_media_profile_slug}", response_model=LocalMediaProfileAPIRead)
def local_media_profiles_detail(local_media_profile_slug: str):
    """Retrieve a Local Media Profile of any type."""
    with db_session() as s:
        return get_local_media_profile(s, local_media_profile_slug)
