from fastapi import APIRouter, HTTPException
from jinja2.exceptions import TemplateError

from backend.api.models.show_assets import ShowAssetRootPreviewRequest, ShowAssetRootPreviewResponse
from backend.app import db_session
from backend.services.show_assets import get_show_asset_root_preview

router = APIRouter()


@router.post("/template/show-root", response_model=ShowAssetRootPreviewResponse)
def show_asset_root_preview(body: ShowAssetRootPreviewRequest):
    """Resolve the selected episode's actual show with the unsaved template.

    Unlike editable example values, real show metadata must determine where
    shared artwork would be written. This endpoint never writes or queues work.
    """
    try:
        with db_session() as session:
            result = get_show_asset_root_preview(
                session, source_id=body.source_id, output_template=body.output_template,
                local_media_profile_id=body.local_media_profile_id,
            )
            return ShowAssetRootPreviewResponse.model_validate(result)
    except (ValueError, TemplateError) as exc:
        raise HTTPException(status_code=422, detail=[{
            "loc": ["body", "outputTemplate"], "msg": str(exc), "type": "value_error",
        }]) from exc
