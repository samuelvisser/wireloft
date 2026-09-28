import pytest
from fastapi import HTTPException


def test_template_preview_reports_unknown_jinja_filter_as_validation_error() -> None:
    from backend.api.endpoints.local_media_profiles.router import local_media_profile_template_preview
    from backend.api.models.local_media_profile import LocalMediaProfileTemplatePreview

    body = LocalMediaProfileTemplatePreview(
        type="show",
        preferred_format="format_audio_only",
        output_template="/downloads/{{ title | regex_replace('x', 'y') }}.ext",
        values={"title": "Example"},
    )

    with pytest.raises(HTTPException) as exc_info:
        local_media_profile_template_preview(body)

    assert exc_info.value.status_code == 422
    assert exc_info.value.detail == [{
        "loc": ["body", "outputTemplate"],
        "msg": "No filter named 'regex_replace'.",
        "type": "value_error",
    }]



def test_preview_plan_treats_incomplete_jinja_as_expected_editor_state(db_session) -> None:
    from backend.api.endpoints.local_media_profiles.preview import get_local_media_profile_preview_plan
    from backend.api.models.local_media_profile_preview import LocalMediaProfilePreviewRequest

    body = LocalMediaProfilePreviewRequest(
        type="show",
        preferred_format="format_audio_only",
        output_template=(
            "{% set extra_num = 'extra' | custom_index %}"
            "{% set plex_year = ' (' ~ meta_show_year ~ ')' if meta_show_year e%}"
            "/downloads/{{ title }}.ext"
        ),
        indexing_values=[{"key": "extra", "name": "Extra"}],
    )

    plan = get_local_media_profile_preview_plan(db_session, body)

    assert plan.simulates_custom_indexes is False
    assert plan.reason is not None
    assert plan.reason.startswith("Invalid Jinja template")
