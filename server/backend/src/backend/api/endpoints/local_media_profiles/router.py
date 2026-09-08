from fastapi import APIRouter, HTTPException, Query, status

from .file_rename import request_local_media_profile_file_rename
from .service import *
from ...models.local_media_profile import *
from ...models.operations import LocalMediaProfileFileRenameOperationAccepted
from backend.app import db_session

router = APIRouter(prefix="/local-media-profiles", tags=["Media Profiles"])

@router.get("", response_model=list[LocalMediaProfileAPIRead])
def local_media_profiles_list():
    """List all media profiles in the system."""
    with db_session() as s:
        return get_local_media_profiles_list(s)


@router.post("", response_model=LocalMediaProfileAPIRead, status_code=status.HTTP_201_CREATED)
def local_media_profiles_create(body: LocalMediaProfileAPICreate):
    """Create a new media profile."""
    with db_session() as s:
        try:
            result = create_local_media_profile(s, body)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.get("/template-sources", response_model=LocalMediaProfileTemplateSources)
def local_media_profile_template_sources(
    type: LocalMediaProfileType = Query(...),
):
    """Return up to ten recent media items for testing an output path template."""
    with db_session() as s:
        try:
            return get_output_template_sources(s, type)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/template-preview", response_model=LocalMediaProfileTemplatePreviewResult)
def local_media_profile_template_preview(body: LocalMediaProfileTemplatePreview):
    """Render an unsaved output path template against editable example values."""
    try:
        return preview_output_template(body)
    except ValueError as exc:
        raise HTTPException(
            status_code=422,
            detail=[{
                "loc": ["body", "outputTemplate"],
                "msg": str(exc),
                "type": "value_error",
            }],
        ) from exc


@router.post(
    "/{local_media_profile_slug}/rename-files",
    response_model=LocalMediaProfileFileRenameOperationAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
def local_media_profile_rename_files(local_media_profile_slug: str):
    """Rename every existing episode file affected by this Local Media Profile."""
    with db_session() as s:
        try:
            result = request_local_media_profile_file_rename(s, local_media_profile_slug)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.get("/{local_media_profile_slug}", response_model=LocalMediaProfileAPIRead)
def local_media_profiles_detail(local_media_profile_slug: str):
    """Retrieve detailed information for a specific media profile."""
    with db_session() as s:
        return get_local_media_profile(s, local_media_profile_slug)


@router.patch("/{local_media_profile_slug}", response_model=LocalMediaProfileAPIRead)
def local_media_profiles_update(local_media_profile_slug: str, body: LocalMediaProfileAPIUpdate):
    """Update an existing media profile's configuration."""
    with db_session() as s:
        try:
            result = update_local_media_profile(s, local_media_profile_slug, body)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise


@router.delete("/{local_media_profile_slug}", response_model=LocalMediaProfileAPIRead)
def local_media_profiles_delete(local_media_profile_slug: str):
    """Delete a media profile from the system."""
    with db_session() as s:
        try:
            result = delete_local_media_profile(s, local_media_profile_slug)
            s.commit()
            return result
        except Exception:
            s.rollback()
            raise
