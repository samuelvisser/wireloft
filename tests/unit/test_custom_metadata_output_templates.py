from types import SimpleNamespace

import pytest
from pydantic import ValidationError


def _episode(*, show_metadata=None):
    return SimpleNamespace(
        show=SimpleNamespace(
            slug="parenting",
            title="Parenting",
            custom_metadata=show_metadata or {},
        ),
        season=None,
        slug="episode-one",
        title="Episode One",
        episode_identifier="ep.1",
        published_date=None,
    )


def _movie(*, movie_metadata=None):
    return SimpleNamespace(
        type="movie",
        slug="run-hide-fight",
        title="Run Hide Fight",
        extended_title=None,
        author_name="Daily Wire",
        mature_rating="R",
        duration=6540,
        release_date=None,
        custom_metadata=movie_metadata or {},
    )


def test_show_and_download_metadata_are_exposed_to_episode_templates() -> None:
    from backend.utils.output_template import (
        SHOW_OUTPUT_TEMPLATE_FIELDS,
        SHOW_OUTPUT_TEMPLATE_METADATA_SCOPES,
        episode_output_template_values,
        render_output_template,
    )

    download_profile = SimpleNamespace(custom_metadata={"library": "Plex"})
    values = episode_output_template_values(
        _episode(show_metadata={"year": "2026"}),
        download_profile,
    )

    assert values["meta_show_year"] == "2026"
    assert values["meta_download_library"] == "Plex"
    assert render_output_template(
        "/downloads/{{ show_title }} ({{ meta_show_year }})/{{ meta_download_library }}/{{ title }}.ext",
        values,
        allowed_fields=SHOW_OUTPUT_TEMPLATE_FIELDS,
        allowed_metadata_scopes=SHOW_OUTPUT_TEMPLATE_METADATA_SCOPES,
    ) == "/downloads/Parenting (2026)/Plex/Episode One.ext"


def test_missing_allowed_custom_metadata_is_an_empty_jinja_value() -> None:
    from backend.utils.output_template import (
        SHOW_OUTPUT_TEMPLATE_FIELDS,
        SHOW_OUTPUT_TEMPLATE_METADATA_SCOPES,
        episode_output_template_values,
        render_output_template,
    )

    values = episode_output_template_values(_episode())
    rendered = render_output_template(
        "/downloads/{{ show_title }}{% if meta_show_year %} ({{ meta_show_year }}){% endif %}/{{ title }}.ext",
        values,
        allowed_fields=SHOW_OUTPUT_TEMPLATE_FIELDS,
        allowed_metadata_scopes=SHOW_OUTPUT_TEMPLATE_METADATA_SCOPES,
    )
    assert rendered == "/downloads/Parenting/Episode One.ext"


def test_movie_metadata_is_exposed_only_to_movie_templates() -> None:
    from backend.utils.output_template import (
        MOVIE_OUTPUT_TEMPLATE_FIELDS,
        MOVIE_OUTPUT_TEMPLATE_METADATA_SCOPES,
        SHOW_OUTPUT_TEMPLATE_FIELDS,
        SHOW_OUTPUT_TEMPLATE_METADATA_SCOPES,
        movie_output_template_values,
        render_output_template,
    )

    values = movie_output_template_values(_movie(movie_metadata={"collection": "Originals"}))
    assert values["meta_movie_collection"] == "Originals"
    assert render_output_template(
        "/downloads/{{ meta_movie_collection }}/{{ movie_title }}.ext",
        values,
        allowed_fields=MOVIE_OUTPUT_TEMPLATE_FIELDS,
        allowed_metadata_scopes=MOVIE_OUTPUT_TEMPLATE_METADATA_SCOPES,
    ) == "/downloads/Originals/Run Hide Fight.ext"

    with pytest.raises(ValueError, match="Unsupported output template variable"):
        render_output_template(
            "/downloads/{{ meta_movie_collection }}/{{ title }}.ext",
            values,
            allowed_fields=SHOW_OUTPUT_TEMPLATE_FIELDS,
            allowed_metadata_scopes=SHOW_OUTPUT_TEMPLATE_METADATA_SCOPES,
        )


def test_download_profile_custom_metadata_uses_base_metadata_namespace() -> None:
    from backend.db.models import PodcastDownloadProfile

    profile = PodcastDownloadProfile(
        show_id=1,
        local_media_profile_id=1,
        enable_profile=True,
        ep_id_type_list=[],
        download_with_countdown=False,
        redownload_final=False,
        download_days_in_past=0,
        download_episode_count=0,
        delete_older_episodes=False,
    )
    profile.set_meta("internal_key", "keep-me")
    profile.replace_custom_metadata({"year": "2026"})

    custom_row = next(item for item in profile.meta_items if item.key == "custom.year")
    assert custom_row.parent_table == "download_profiles"
    assert profile.custom_metadata == {"year": "2026"}

    profile.replace_custom_metadata({"year": "2027", "library": "Plex"})
    assert profile.get_meta("internal_key") == "keep-me"
    assert profile.custom_metadata == {"year": "2027", "library": "Plex"}


def test_custom_metadata_request_requires_jinja_safe_keys() -> None:
    from backend.api.models.custom_metadata import CustomMetadataAPIUpdate

    request = CustomMetadataAPIUpdate(customMetadata={"release_year": "2026"})
    assert request.custom_metadata == {"release_year": "2026"}

    with pytest.raises(ValidationError):
        CustomMetadataAPIUpdate(customMetadata={"Release year": "2026"})
