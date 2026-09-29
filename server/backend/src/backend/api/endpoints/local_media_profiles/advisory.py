from fastapi import APIRouter

from backend.api.models.output_template_advisory import (
    CustomIndexAdvisoryRequest,
    CustomIndexAdvisoryResultRead,
)
from backend.utils.jinja_analysis.custom_index_advisory import get_custom_index_advisories
from backend.utils.output_template_jinja import create_output_template_environment


router = APIRouter(prefix="/advisory")


@router.post("/custom-index", response_model=CustomIndexAdvisoryResultRead)
def custom_index_advisory(body: CustomIndexAdvisoryRequest):
    """Read-only advice for the unsaved form; no episode, DB or filesystem work."""
    return get_custom_index_advisories(
        body.output_template,
        definition_keys=body.indexing_value_keys,
        environment=create_output_template_environment(),
    )
