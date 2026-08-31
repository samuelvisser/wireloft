from __future__ import annotations

from datetime import datetime, timedelta

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
    )
    template = (
        "/downloads/{{ movie_title }}{% if year %} ({{ year }}){% endif %}/{{ title }}"
        "{% if media_type != 'movie' %}-{{ media_type }}{% endif %}.ext"
    )

    movie_path = resolve_movie_output_path(template, movie=movie)
    trailer_path = resolve_movie_output_path(template, movie=movie, media_item=trailer)

    assert movie_path == (tmp_path / "Example Movie" / "Example Movie.ext").resolve()
    assert trailer_path == (tmp_path / "Example Movie" / "Official Trailer-trailer.ext").resolve()


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


def test_legacy_placeholders_are_canonicalized_without_changing_jinja_blocks():
    from backend.utils.output_template import upgrade_legacy_output_template

    assert upgrade_legacy_output_template(
        "/downloads/{show}/{% if year %}{{ year }}{% endif %}/{episode}.ext"
    ) == (
        "/downloads/{{ show }}/{% if year %}{{ year }}{% endif %}/{{ episode }}.ext"
    )


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


def test_preview_uses_edited_values_and_returns_referenced_variables():
    from backend.api.endpoints.local_media_profiles.service import preview_output_template
    from backend.api.models.local_media_profile import LocalMediaProfileTemplatePreview

    result = preview_output_template(LocalMediaProfileTemplatePreview(
        type="movie",
        output_template=(
            "/downloads/{{ movie_title }}/{{ title }}"
            "{% if media_type != 'movie' %}-{{ media_type }}{% endif %}.ext"
        ),
        values={"movie_title": "Lady Ballers", "title": "Lady Ballers", "media_type": "movie"},
    ))

    assert result.output_path == "/downloads/Lady Ballers/Lady Ballers.ext"
    assert result.used_variables == ["media_type", "movie_title", "title"]
    assert "movie" not in result.used_variables
