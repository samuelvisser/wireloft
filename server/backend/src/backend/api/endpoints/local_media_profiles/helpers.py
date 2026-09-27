from __future__ import annotations

import logging

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.api.models.local_media_profile import LocalMediaProfileAPIBaseIn
from backend.db.models import LocalMediaProfileBase
from backend.utils.jinja_analysis.comparison import OutputOverlap
from backend.utils.output_template import _sanitize_emitted_output_value, finalize_output_path
from backend.utils.output_template_analysis import analyze_profile_outputs, compare_profile_outputs
from backend.utils.output_template_jinja import create_output_template_environment

logger = logging.getLogger(__name__)


def ensure_unique_profile_settings(
    s: Session,
    profile_model: type[LocalMediaProfileBase],
    body: LocalMediaProfileAPIBaseIn,
    *,
    exclude_id: int | None = None,
) -> None:
    query = s.query(profile_model)
    if exclude_id is not None:
        query = query.filter(LocalMediaProfileBase.id != exclude_id)

    environment = create_output_template_environment()
    environment.finalize = _sanitize_emitted_output_value
    candidate = analyze_profile_outputs(
        body.output_template, body.type, body.preferred_format,
        environment=environment, namespace="candidate",
    )
    for existing in query.all():
        if (
            existing.output_template == body.output_template
            and existing.preferred_format == body.preferred_format
        ):
            raise HTTPException(
                status_code=409,
                detail=[{
                    "loc": ["body", "outputTemplate"],
                    "msg": "A Local Media Profile with this output path template and preferred format already exists",
                    "type": "unique_violation",
                }],
            )

        previous = analyze_profile_outputs(
            existing.output_template, existing.type, existing.preferred_format,
            environment=environment, namespace=f"profile:{existing.id}",
        )
        comparison = compare_profile_outputs(
            candidate, previous, environment=environment, finalize_path=finalize_output_path,
        )
        if comparison.status == OutputOverlap.OVERLAP:
            raise HTTPException(
                status_code=409,
                detail=[{
                    "loc": ["body", "outputTemplate"],
                    "msg": (
                        "Output template can produce the same file as Local Media Profile "
                        f"'{existing.name}'. Choose a different output path."
                    ),
                    "type": "output_path_collision",
                }],
            )
        if comparison.status == OutputOverlap.UNKNOWN:
            # Static validation is not a filesystem reservation. Do not reject
            # valid advanced templates merely because their expressions are not
            # comparable; actual download/rename collision guards remain final.
            logger.debug("Output comparison with Local Media Profile %s is inconclusive: %s",
                         existing.id, comparison.reason)
