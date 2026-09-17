from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta

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


def _add_episodes(
    session: Session,
    show,
    *,
    count: int,
    newest_at: datetime,
):
    from backend.db.models import Episode, Season
    from backend.utils.helpers import generate_uuid

    season = Season(show=show, index=1, slug="season-1", name="Season 1")
    session.add(season)
    session.flush()

    for index in range(count):
        episode_number = index + 1
        published_at = newest_at - timedelta(hours=index)
        episode = Episode(
            uuid=generate_uuid(),
            type="episode",
            show=show,
            season=season,
            index=episode_number,
            episode_identifier=str(episode_number),
            slug=f"{show.slug}-episode-{episode_number}",
            title=f"Episode {episode_number}",
            duration=100.0,
            publish_status="published_final",
            sharing_url=f"https://example.test/{show.slug}/{episode_number}",
            published_date=published_at,
        )
        session.add(episode)
    session.flush()


def test_series_sources_are_evenly_distributed_across_available_shows(db_session):
    from backend.api.endpoints.local_media_profiles.template_source_selection import (
        select_show_template_source_episodes,
    )
    from backend.types.local_media_profile_types import ShowLocalMediaProfileScope
    from backend.types.show_types import ShowType

    newest = datetime(2026, 9, 17, 12, 0, 0)
    shows = []
    for index in range(4):
        show = _make_show(db_session, slug=f"series-{index}", show_type=ShowType.SERIES.value)
        _add_episodes(db_session, show, count=3, newest_at=newest - timedelta(days=index))
        shows.append(show)

    episodes = select_show_template_source_episodes(
        db_session,
        ShowLocalMediaProfileScope.SERIES,
    )

    counts = Counter(episode.show_id for episode in episodes)
    assert len(episodes) == 10
    assert set(counts) == {show.id for show in shows}
    assert sorted(counts.values()) == [2, 2, 3, 3]


def test_ten_or_more_shows_contribute_one_episode_each(db_session):
    from backend.api.endpoints.local_media_profiles.template_source_selection import (
        select_show_template_source_episodes,
    )
    from backend.types.local_media_profile_types import ShowLocalMediaProfileScope
    from backend.types.show_types import ShowType

    newest = datetime(2026, 9, 17, 12, 0, 0)
    for index in range(12):
        show = _make_show(db_session, slug=f"podcast-{index}", show_type=ShowType.PODCAST.value)
        _add_episodes(db_session, show, count=2, newest_at=newest - timedelta(hours=index))

    episodes = select_show_template_source_episodes(
        db_session,
        ShowLocalMediaProfileScope.PODCAST,
    )

    assert len(episodes) == 10
    assert len({episode.show_id for episode in episodes}) == 10


def test_scope_both_targets_five_examples_per_show_type(db_session):
    from backend.api.endpoints.local_media_profiles.template_source_selection import (
        select_show_template_source_episodes,
    )
    from backend.types.local_media_profile_types import ShowLocalMediaProfileScope
    from backend.types.show_types import ShowType

    newest = datetime(2026, 9, 17, 12, 0, 0)
    for index in range(3):
        show = _make_show(db_session, slug=f"podcast-{index}", show_type=ShowType.PODCAST.value)
        _add_episodes(db_session, show, count=2, newest_at=newest - timedelta(hours=index))
    for index in range(2):
        show = _make_show(db_session, slug=f"series-{index}", show_type=ShowType.SERIES.value)
        _add_episodes(db_session, show, count=3, newest_at=newest - timedelta(hours=index))

    episodes = select_show_template_source_episodes(
        db_session,
        ShowLocalMediaProfileScope.BOTH,
    )

    type_counts = Counter(episode.show.type for episode in episodes)
    assert len(episodes) == 10
    assert type_counts == {
        ShowType.PODCAST.value: 5,
        ShowType.SERIES.value: 5,
    }


def test_single_show_scope_excludes_the_other_show_type(db_session):
    from backend.api.endpoints.local_media_profiles.template_source_selection import (
        select_show_template_source_episodes,
    )
    from backend.types.local_media_profile_types import ShowLocalMediaProfileScope
    from backend.types.show_types import ShowType

    newest = datetime(2026, 9, 17, 12, 0, 0)
    podcast = _make_show(db_session, slug="podcast", show_type=ShowType.PODCAST.value)
    series = _make_show(db_session, slug="series", show_type=ShowType.SERIES.value)
    _add_episodes(db_session, podcast, count=3, newest_at=newest)
    _add_episodes(db_session, series, count=3, newest_at=newest)

    episodes = select_show_template_source_episodes(
        db_session,
        ShowLocalMediaProfileScope.SERIES,
    )

    assert episodes
    assert {episode.show.type for episode in episodes} == {ShowType.SERIES.value}
