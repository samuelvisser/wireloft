from __future__ import annotations

from datetime import date, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


@pytest.fixture
def db_session():
    import backend.db.models  # noqa: F401
    from backend.db import Base

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()
    engine.dispose()


def _make_show(session: Session, *, slug: str, show_type: str):
    from backend.db.models import Show
    from backend.types.show_types import EpisodeIdentifier

    show = Show(
        uuid=f"{slug}-uuid",
        slug=slug,
        title=slug.replace("-", " ").title(),
        description=None,
        sharing_url=f"https://example.test/{slug}",
        membership_level="FREE",
        type=show_type,
        episode_identifier=EpisodeIdentifier.NUMBERED.value,
        author_name="Host",
        author_slug="host",
    )
    session.add(show)
    session.flush()
    return show


def _add_episode(
    session: Session,
    show,
    *,
    index: int,
    title: str | None = None,
    season_name: str = "Season 1",
):
    from backend.db.models import Episode, Season
    from backend.utils.helpers import generate_uuid

    season = next((item for item in show.seasons if item.name == season_name), None)
    if season is None:
        season = Season(
            show=show,
            index=len(show.seasons) + 1,
            slug=f"season-{len(show.seasons) + 1}",
            name=season_name,
        )
        session.add(season)
        session.flush()

    episode = Episode(
        uuid=generate_uuid(),
        type="episode",
        show=show,
        season=season,
        index=index,
        episode_identifier=str(index),
        slug=f"{show.slug}-episode-{index}",
        title=title or f"Episode {index}",
        duration=100.0,
        publish_status="published_final",
        sharing_url=f"https://example.test/{show.slug}/{index}",
        published_date=datetime(2026, 9, index, 12, 0, 0),
    )
    session.add(episode)
    session.flush()
    return episode


def test_show_sources_page_through_every_episode_in_scope(db_session):
    from backend.api.endpoints.local_media_profiles.output_template import (
        get_output_template_source_page,
    )
    from backend.types.local_media_profile_types import (
        LocalMediaProfileType,
        ShowLocalMediaProfileScope,
    )
    from backend.types.show_types import ShowType

    podcast = _make_show(db_session, slug="alpha-podcast", show_type=ShowType.PODCAST.value)
    series = _make_show(db_session, slug="beta-series", show_type=ShowType.SERIES.value)
    for index in range(1, 5):
        _add_episode(db_session, podcast, index=index)
    for index in range(1, 4):
        _add_episode(db_session, series, index=index)

    first = get_output_template_source_page(
        db_session,
        LocalMediaProfileType.SHOW,
        ShowLocalMediaProfileScope.PODCAST,
        offset=0,
        limit=2,
    )
    second = get_output_template_source_page(
        db_session,
        LocalMediaProfileType.SHOW,
        ShowLocalMediaProfileScope.PODCAST,
        offset=2,
        limit=2,
    )

    assert first.has_more is True
    assert second.has_more is False
    assert [source.values["episode_number"] for source in first.items + second.items] == [
        "1", "2", "3", "4",
    ]
    assert {source.values["show_title"] for source in first.items + second.items} == {
        "Alpha Podcast",
    }


def test_show_source_search_can_match_parent_and_episode_terms(db_session):
    from backend.api.endpoints.local_media_profiles.output_template import (
        get_output_template_source_page,
    )
    from backend.types.local_media_profile_types import LocalMediaProfileType
    from backend.types.show_types import ShowType

    show = _make_show(
        db_session,
        slug="biblical-series-genesis",
        show_type=ShowType.SERIES.value,
    )
    _add_episode(db_session, show, index=1, title="Jacob: Wrestling with God")
    _add_episode(db_session, show, index=2, title="Joseph and the Coat of Many Colors")

    result = get_output_template_source_page(
        db_session,
        LocalMediaProfileType.SHOW,
        search="Genesis Jacob",
        limit=30,
    )

    assert [source.values["episode_title"] for source in result.items] == [
        "Jacob: Wrestling with God",
    ]


def test_show_source_search_ranks_the_strongest_phrase_match_first(db_session):
    from backend.api.endpoints.local_media_profiles.output_template import (
        get_output_template_source_page,
    )
    from backend.types.local_media_profile_types import LocalMediaProfileType
    from backend.types.show_types import ShowType

    show = _make_show(
        db_session,
        slug="the-ben-shapiro-show",
        show_type=ShowType.PODCAST.value,
    )
    _add_episode(db_session, show, index=1, title="Trump Gets It Right On Radical Islam")
    _add_episode(db_session, show, index=2, title="Radical Islam's Front Group EXPOSED By Texas!")
    _add_episode(db_session, show, index=3, title="Radical Islam INVADES The US Senate?!")
    _add_episode(db_session, show, index=4, title="Radical Islam Is On The March")

    result = get_output_template_source_page(
        db_session,
        LocalMediaProfileType.SHOW,
        search="Radical Islam is on the",
    )

    assert result.items[0].values["episode_title"] == "Radical Islam Is On The March"


def test_show_scope_excludes_other_show_types_even_when_search_matches(db_session):
    from backend.api.endpoints.local_media_profiles.output_template import (
        get_output_template_source_page,
    )
    from backend.types.local_media_profile_types import (
        LocalMediaProfileType,
        ShowLocalMediaProfileScope,
    )
    from backend.types.show_types import ShowType

    podcast = _make_show(db_session, slug="shared-podcast", show_type=ShowType.PODCAST.value)
    series = _make_show(db_session, slug="shared-series", show_type=ShowType.SERIES.value)
    _add_episode(db_session, podcast, index=1, title="Shared title")
    _add_episode(db_session, series, index=1, title="Shared title")

    result = get_output_template_source_page(
        db_session,
        LocalMediaProfileType.SHOW,
        ShowLocalMediaProfileScope.SERIES,
        search="Shared",
    )

    assert len(result.items) == 1
    assert result.items[0].values["show_title"] == "Shared Series"


def test_movie_sources_include_movies_and_every_extra_with_server_search(db_session):
    from backend.api.endpoints.local_media_profiles.output_template import (
        get_output_template_source_page,
    )
    from backend.db.models import Movie, MovieExtra
    from backend.types.local_media_profile_types import LocalMediaProfileType

    movie = Movie(
        uuid="alpha-movie",
        type="movie",
        slug="alpha-movie",
        title="Alpha Movie",
        author_name="Alpha Studio",
        description=None,
        duration=6000,
        release_date=date(2024, 1, 2),
    )
    movie.movie_extras.extend([
        MovieExtra(
            uuid="alpha-trailer",
            type="movie_extra",
            movie_extra_type="trailer",
            slug="alpha-trailer",
            title="Official Trailer",
            description=None,
            duration=120,
            published_date=datetime(2024, 1, 3, 12, 0, 0),
        ),
        MovieExtra(
            uuid="alpha-interview",
            type="movie_extra",
            movie_extra_type="interview",
            slug="alpha-interview",
            title="Cast Interview",
            description=None,
            duration=300,
            published_date=datetime(2024, 1, 4, 12, 0, 0),
        ),
    ])
    db_session.add(movie)
    db_session.commit()

    all_sources = get_output_template_source_page(
        db_session,
        LocalMediaProfileType.MOVIE,
        limit=2,
    )
    last_source = get_output_template_source_page(
        db_session,
        LocalMediaProfileType.MOVIE,
        offset=2,
        limit=2,
    )
    trailer_search = get_output_template_source_page(
        db_session,
        LocalMediaProfileType.MOVIE,
        search="Alpha Trailer",
    )

    assert all_sources.has_more is True
    assert last_source.has_more is False
    combined = all_sources.items + last_source.items
    assert [source.values["media_type"] for source in combined] == [
        "movie", "interview", "trailer",
    ]
    assert {source.values["movie_title"] for source in combined} == {"Alpha Movie"}
    assert [source.values["title"] for source in trailer_search.items] == ["Official Trailer"]


def test_movie_source_search_ranks_matching_extra_title_by_relevance(db_session):
    from backend.api.endpoints.local_media_profiles.output_template import (
        get_output_template_source_page,
    )
    from backend.db.models import Movie, MovieExtra
    from backend.types.local_media_profile_types import LocalMediaProfileType

    movie = Movie(
        uuid="radical-islam-movie",
        type="movie",
        slug="radical-islam-movie",
        title="The Radical Islam Documentary",
        description=None,
        duration=6000,
        release_date=date(2024, 1, 2),
    )
    movie.movie_extras.extend([
        MovieExtra(
            uuid="radical-islam-commentary",
            type="movie_extra",
            movie_extra_type="commentary",
            slug="radical-islam-commentary",
            title="Trump Gets It Right On Radical Islam",
            description=None,
            duration=120,
            published_date=datetime(2024, 1, 3, 12, 0, 0),
        ),
        MovieExtra(
            uuid="radical-islam-march",
            type="movie_extra",
            movie_extra_type="commentary",
            slug="radical-islam-march",
            title="Radical Islam Is On The March",
            description=None,
            duration=300,
            published_date=datetime(2024, 1, 4, 12, 0, 0),
        ),
    ])
    db_session.add(movie)
    db_session.commit()

    result = get_output_template_source_page(
        db_session,
        LocalMediaProfileType.MOVIE,
        search="Radical Islam is on the",
    )

    assert [source.values["title"] for source in result.items] == [
        "Radical Islam Is On The March",
        "Trump Gets It Right On Radical Islam",
    ]


def test_empty_library_uses_fallback_but_empty_search_does_not(db_session):
    from backend.api.endpoints.local_media_profiles.output_template import (
        get_output_template_source_page,
    )
    from backend.types.local_media_profile_types import LocalMediaProfileType

    fallback = get_output_template_source_page(
        db_session,
        LocalMediaProfileType.MOVIE,
    )
    search = get_output_template_source_page(
        db_session,
        LocalMediaProfileType.MOVIE,
        search="missing",
    )

    assert len(fallback.items) == 1
    assert fallback.items[0].fallback is True
    assert fallback.items[0].values["media_type"] == "movie"
    assert search.items == []
    assert search.has_more is False
