from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _new_session() -> tuple[Session, object]:
    import backend.db.models  # noqa: F401
    from backend.db import Base

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine), engine


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
        downloaded_date=None,
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
        downloaded_date=None,
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
        dw_id="movie-123",
        author_name="Movie Author",
        mature_rating="PG-13",
        description=None,
        downloaded_date=None,
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
        dw_id="extra-456",
        description=None,
        downloaded_date=None,
        duration=120.6,
        published_date=datetime(2021, 6, 7, 8, 9, 10),
    )

    movie_values = movie_output_template_values(movie)
    extra_values = movie_output_template_values(movie, extra)

    assert movie_values.keys() == extra_values.keys() == MOVIE_OUTPUT_TEMPLATE_FIELDS
    assert "movie" not in movie_values
    assert movie_values["movie_slug"] == movie_values["slug"] == "parent-movie"
    assert movie_values["movie_title"] == movie_values["title"] == "Parent Movie"
    assert movie_values["movie_year"] == movie_values["year"] == "2020"

    assert extra_values["movie_slug"] == "parent-movie"
    assert extra_values["slug"] == "official-trailer"
    assert extra_values["movie_title"] == "Parent Movie"
    assert extra_values["title"] == "Official Trailer"
    assert extra_values["movie_extended_title"] == "Parent Movie | Extended"
    assert extra_values["extended_title"] == "Official Trailer"
    assert extra_values["movie_dw_id"] == "movie-123"
    assert extra_values["dw_id"] == "extra-456"
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
    from backend.api.models.local_media_profile import LocalMediaProfileAPICreate
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
        LocalMediaProfileAPICreate.model_validate({
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


def test_template_sources_use_only_ten_latest_episodes_and_fallback_for_empty_movies():
    from backend.api.endpoints.local_media_profiles.service import get_output_template_sources
    from backend.db.models import Episode, Season, Show
    from backend.types.local_media_profile_types import LocalMediaProfileType
    from backend.types.show_types import EpisodeIdentifier, ShowType

    session, engine = _new_session()
    show = Show(
        uuid="show-uuid",
        slug="example-show",
        title="Example Show",
        description=None,
        sharing_url="https://example.test/show",
        membership_level="FREE",
        type=ShowType.PODCAST.value,
        episode_identifier=EpisodeIdentifier.NUMBERED.value,
        author_name="Host",
        author_slug="host",
    )
    season = Season(show=show, index=1, slug="season-1", name="Season 1")
    published = datetime(2026, 8, 1, 12, 0, 0)
    episodes = [
        Episode(
            uuid=f"episode-{index}",
            type="episode",
            show=show,
            season=season,
            index=index,
            episode_identifier=f"ep.{index}",
            slug=f"episode-{index}",
            title=f"Episode {index}",
            description=None,
            downloaded_date=None,
            duration=60,
            publish_status="published_final",
            sharing_url=f"https://example.test/episode-{index}",
            published_date=published + timedelta(days=index),
        )
        for index in range(1, 13)
    ]
    session.add_all([show, season, *episodes])
    session.commit()

    show_sources = get_output_template_sources(session, LocalMediaProfileType.SHOW)
    movie_sources = get_output_template_sources(session, LocalMediaProfileType.MOVIE)

    assert len(show_sources.sources) == 10
    assert show_sources.sources[0].label == "Example Show — Episode 12"
    assert show_sources.sources[-1].label == "Example Show — Episode 3"
    assert not any(source.fallback for source in show_sources.sources)
    assert len(movie_sources.sources) == 1
    assert movie_sources.sources[0].fallback is True
    assert movie_sources.sources[0].values["media_type"] == "movie"

    session.close()
    engine.dispose()


def test_movie_template_sources_include_local_extras_parent_first_and_limit_to_twenty():
    from backend.api.endpoints.local_media_profiles.service import get_output_template_sources
    from backend.db.models import Movie, MovieExtra
    from backend.types.local_media_profile_types import LocalMediaProfileType

    session, engine = _new_session()
    movies = []
    for index in range(11):
        movie = Movie(
            uuid=f"movie-{index}",
            type="movie",
            slug=f"movie-{index}",
            title=f"Movie {index}",
            description=None,
            downloaded_date=None,
            duration=6000,
            release_date=date(2020 + index, 1, 2),
        )
        movie.movie_extras.extend([
            MovieExtra(
                uuid=f"movie-{index}-trailer",
                type="movie_extra",
                movie_extra_type="trailer",
                slug=f"movie-{index}-trailer",
                title=f"Movie {index} Trailer",
                description=None,
                downloaded_date=None,
                duration=120,
                published_date=datetime(2021 + index, 3, 4, 5, 6, 7),
            ),
            MovieExtra(
                uuid=f"movie-{index}-interview",
                type="movie_extra",
                movie_extra_type="interview",
                slug=f"movie-{index}-interview",
                title=f"Movie {index} Interview",
                description=None,
                downloaded_date=None,
                duration=300,
                published_date=datetime(2021 + index, 4, 5, 6, 7, 8),
            ),
        ])
        movies.append(movie)
    session.add_all(movies)
    session.commit()

    sources = get_output_template_sources(session, LocalMediaProfileType.MOVIE).sources

    assert len(sources) == 20
    assert sources[0].id.startswith("movie:")
    assert sources[1].id.startswith("movie-extra:")
    assert sources[2].id.startswith("movie-extra:")
    assert sources[1].label.startswith("\u00a0\u00a0↳ ")
    assert sources[1].values["movie_title"] == sources[0].values["movie_title"]
    assert sources[1].values["title"] != sources[0].values["title"]
    assert sources[1].values["media_type"] == "trailer"
    assert sources[1].values["movie_year"] == sources[0].values["year"]
    assert sources[1].values["year"] != sources[1].values["movie_year"]
    assert all(source.fallback is False for source in sources)

    session.close()
    engine.dispose()


def test_preview_uses_edited_values_and_returns_referenced_variables():
    from backend.api.endpoints.local_media_profiles.service import preview_output_template
    from backend.api.models.local_media_profile import LocalMediaProfileTemplatePreview

    result = preview_output_template(LocalMediaProfileTemplatePreview(
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


def test_preview_resolves_audio_extension_in_backend():
    from backend.api.endpoints.local_media_profiles.service import preview_output_template
    from backend.api.models.local_media_profile import LocalMediaProfileTemplatePreview

    result = preview_output_template(LocalMediaProfileTemplatePreview(
        type="show",
        preferred_format="format_audio_only",
        output_template="/downloads/{{ show_title }}/{{ episode_title }}.ext",
        values={"show_title": "Example Show", "episode_title": "Episode One"},
    ))

    assert result.output_path == "/downloads/Example Show/Episode One.m4a"
