import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


@pytest.fixture
def db_session():
    import backend.db.models  # noqa: F401
    from backend.db import Base

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_template_preview_reports_unknown_jinja_filter_as_output_error(db_session) -> None:
    from backend.api.endpoints.local_media_profiles.preview import get_local_media_profile_preview
    from backend.api.models.local_media_profile_preview import LocalMediaProfilePreviewRequest

    body = LocalMediaProfilePreviewRequest(
        type="show",
        preferred_format="format_audio_only",
        output_template="/downloads/{{ title | not_a_filter('x', 'y') }}.ext",
        values={"title": "Example"},
    )

    result = get_local_media_profile_preview(db_session, body)

    assert result.output.output_path is None
    assert result.output.error.startswith("No filter named 'not_a_filter'.")


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
