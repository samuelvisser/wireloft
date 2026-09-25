from __future__ import annotations

from datetime import date, datetime

import pytest
def test_jinja_conditionals_omit_missing_year_and_suffix_movie_extras(tmp_path, monkeypatch):
    from backend.db.models import Movie, MovieExtra
    from backend.types.media_types import MediaType
    from backend.utils.output_template import resolve_movie_output_path
    from config import get_settings

    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)
    movie = Movie(
        uuid="movie-uuid",
        type=MediaType.MOVIE.value,
        slug="example-movie",
        title="Example Movie",
        description=None,
        duration=6000,
        release_date=date(2020, 5, 4),
    )
    trailer = MovieExtra(
        uuid="trailer-uuid",
        type=MediaType.MOVIE_EXTRA.value,
        movie=movie,
        movie_extra_type="trailer",
        slug="example-trailer",
        title="Official Trailer",
        description=None,
        duration=120,
        published_date=datetime(2021, 6, 7, 8, 9, 10),
    )
    template = (
        "/downloads/{{ movie_title }}{% if movie_year %} ({{ movie_year }}){% endif %}/"
        "{{ title }}{% if year %} ({{ year }}){% endif %}"
        "{% if media_type != 'movie' %}-{{ media_type }}{% endif %}.ext"
    )

    movie_path = resolve_movie_output_path(template, movie=movie)
    trailer_path = resolve_movie_output_path(template, movie=movie, media_item=trailer)

    assert movie_path == (tmp_path / "Example Movie (2020)" / "Example Movie (2020).ext").resolve()
    assert trailer_path == (
        tmp_path / "Example Movie (2020)" / "Official Trailer (2021)-trailer.ext"
    ).resolve()


def test_movie_variables_separate_parent_movie_from_current_media() -> None:
    from backend.db.models import Movie, MovieExtra
    from backend.types.media_types import MediaType
    from backend.utils.output_template import (
        MOVIE_OUTPUT_TEMPLATE_FIELDS,
        movie_output_template_values,
    )

    movie = Movie(
        uuid="movie-context",
        type=MediaType.MOVIE.value,
        slug="parent-movie",
        title="Parent Movie",
        extended_title="Parent Movie | Extended",
        author_name="Movie Author",
        mature_rating="PG-13",
        description=None,
        duration=6000.4,
        release_date=date(2020, 5, 4),
    )
    extra = MovieExtra(
        uuid="extra-context",
        type=MediaType.MOVIE_EXTRA.value,
        movie=movie,
        movie_extra_type="trailer",
        slug="official-trailer",
        title="Official Trailer",
        description=None,
        duration=120.6,
        published_date=datetime(2021, 6, 7, 8, 9, 10),
    )

    movie_values = movie_output_template_values(movie)
    extra_values = movie_output_template_values(movie, extra)

    assert movie_values.keys() == extra_values.keys() == MOVIE_OUTPUT_TEMPLATE_FIELDS
    assert "movie" not in movie_values
    assert "movie_dw_id" not in movie_values
    assert "dw_id" not in movie_values
    assert movie_values["movie_slug"] == movie_values["slug"] == "parent-movie"
    assert movie_values["movie_title"] == movie_values["title"] == "Parent Movie"
    assert movie_values["movie_year"] == movie_values["year"] == "2020"

    assert extra_values["movie_slug"] == "parent-movie"
    assert extra_values["slug"] == "official-trailer"
    assert extra_values["movie_title"] == "Parent Movie"
    assert extra_values["title"] == "Official Trailer"
    assert extra_values["movie_extended_title"] == "Parent Movie | Extended"
    assert extra_values["extended_title"] == "Official Trailer"
    assert extra_values["movie_author"] == "Movie Author"
    assert extra_values["author"] == ""
    assert extra_values["movie_mature_rating"] == "PG-13"
    assert extra_values["mature_rating"] == extra_values["rating"] == ""
    assert extra_values["movie_duration_seconds"] == "6000"
    assert extra_values["duration_seconds"] == "121"
    assert extra_values["media_type"] == "trailer"
    assert extra_values["movie_datetime"] == "2020-05-04 00:00:00"
    assert extra_values["movie_year"] == "2020"
    assert extra_values["datetime"] == "2021-06-07 08:09:10"
    assert extra_values["year"] == "2021"


def test_jinja_validation_reports_syntax_and_unknown_variables():
    from backend.utils.output_template import (
        SHOW_OUTPUT_TEMPLATE_FIELDS,
        validate_output_template_fields,
    )

    with pytest.raises(ValueError, match="Invalid Jinja template"):
        validate_output_template_fields(
            "/downloads/{{ show }/{% endif %}/episode.ext",
            allowed_fields=SHOW_OUTPUT_TEMPLATE_FIELDS,
        )

    with pytest.raises(ValueError, match="unknown_value"):
        validate_output_template_fields(
            "/downloads/{{ show }}/{{ unknown_value }}.ext",
            allowed_fields=SHOW_OUTPUT_TEMPLATE_FIELDS,
        )


def test_single_brace_placeholders_are_rejected_instead_of_upgraded():
    from backend.api.models.show_local_media_profile import ShowLocalMediaProfileAPICreate
    from backend.utils.output_template import (
        SHOW_OUTPUT_TEMPLATE_FIELDS,
        validate_output_template_fields,
    )

    old_style = "/downloads/{show}/{episode}.ext"
    with pytest.raises(ValueError, match="Jinja syntax"):
        validate_output_template_fields(
            old_style,
            allowed_fields=SHOW_OUTPUT_TEMPLATE_FIELDS,
        )

    with pytest.raises(ValueError, match="Jinja syntax"):
        ShowLocalMediaProfileAPICreate.model_validate({
            "type": "show",
            "name": "Old style",
            "outputTemplate": old_style,
            "preferredFormat": "format_audio_only",
        })

    compact_jinja = "/downloads/{{show}}/{{episode}}.ext"
    assert validate_output_template_fields(
        compact_jinja,
        allowed_fields=SHOW_OUTPUT_TEMPLATE_FIELDS,
    ) == compact_jinja


def test_preview_uses_edited_values_and_returns_referenced_variables():
    from backend.api.endpoints.local_media_profiles.output_template import get_output_template_preview
    from backend.api.models.local_media_profile import LocalMediaProfileTemplatePreview

    result = get_output_template_preview(None, LocalMediaProfileTemplatePreview(
        type="movie",
        preferred_format="format_1080p",
        output_template=(
            "/downloads/{{ movie_title }}/{{ title }}"
            "{% if media_type != 'movie' %}-{{ media_type }}{% endif %}.ext"
        ),
        values={"movie_title": "Lady Ballers", "title": "Lady Ballers", "media_type": "movie"},
    ))

    assert result.output_path == "/downloads/Lady Ballers/Lady Ballers.mp4"
    assert result.used_variables == ["media_type", "movie_title", "title"]
    assert "movie" not in result.used_variables


def test_preview_prefix_error_includes_actual_rendered_output():
    from backend.api.endpoints.local_media_profiles.output_template import get_output_template_preview
    from backend.api.models.local_media_profile import LocalMediaProfileTemplatePreview

    preview = LocalMediaProfileTemplatePreview(
        type="show",
        preferred_format="format_audio_only",
        output_template="{{ show_title }}/downloads/{{ episode_title }}.ext",
        values={"show_title": "Example Show", "episode_title": "Episode One"},
    )

    with pytest.raises(
        ValueError,
        match=r"Actual output: 'Example Show/downloads/Episode One\.ext'",
    ):
        get_output_template_preview(None, preview)


def test_preview_resolves_audio_extension_in_backend():
    from backend.api.endpoints.local_media_profiles.output_template import get_output_template_preview
    from backend.api.models.local_media_profile import LocalMediaProfileTemplatePreview

    result = get_output_template_preview(None, LocalMediaProfileTemplatePreview(
        type="show",
        preferred_format="format_audio_only",
        output_template="/downloads/{{ show_title }}/{{ episode_title }}.ext",
        values={"show_title": "Example Show", "episode_title": "Episode One"},
    ))

    assert result.output_path == "/downloads/Example Show/Episode One.m4a"


def test_jinja_logic_uses_raw_unsanitized_values(monkeypatch) -> None:
    from backend.utils.output_template import SHOW_OUTPUT_TEMPLATE_FIELDS, render_output_template
    from config import get_settings
    from config.settings.submodels import FilenameRestrictionMode

    monkeypatch.setattr(
        get_settings().download_settings,
        "filename_restriction_mode",
        FilenameRestrictionMode.WINDOWS,
    )

    rendered = render_output_template(
        (
            "{% set is_extra = episode_type == 'aux' %}"
            "/downloads/{% if is_extra %}extra{% else %}regular{% endif %}-{{ episode_type }}.ext"
        ),
        {"episode_type": "aux"},
        allowed_fields=SHOW_OUTPUT_TEMPLATE_FIELDS,
    )

    assert rendered == "/downloads/extra-aux.ext"


def test_preview_does_not_apply_filename_restrictions(monkeypatch) -> None:
    from backend.api.endpoints.local_media_profiles.output_template import get_output_template_preview
    from backend.api.models.local_media_profile import LocalMediaProfileTemplatePreview
    from config import get_settings
    from config.settings.submodels import FilenameRestrictionMode

    monkeypatch.setattr(
        get_settings().download_settings,
        "filename_restriction_mode",
        FilenameRestrictionMode.WINDOWS,
    )

    result = get_output_template_preview(LocalMediaProfileTemplatePreview(
        type="show",
        preferred_format="format_audio_only",
        output_template="/downloads/{{ episode_type }}.ext",
        values={"episode_type": "aux"},
    ))

    assert result.output_path == "/downloads/aux.m4a"
