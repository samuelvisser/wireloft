from __future__ import annotations

from datetime import datetime

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_rss_stream_profile_defaults_to_episode_and_auxiliary():
    from backend.api.models.rss_stream_profile import RssStreamProfileAPICreate

    profile = RssStreamProfileAPICreate(
        show_id=1,
        title="Test Show",
        enable_profile=True,
        use_downloads=False,
        use_dw_stream=True,
        preferred_format="format_1080p",
        prefer_exact_match=False,
    )

    assert profile.ep_id_type_list == ["ep", "aux"]


def test_audio_only_rss_stream_profile_defaults_video_output_mode_to_null():
    from backend.api.models.rss_stream_profile import RssStreamProfileAPICreate

    profile = RssStreamProfileAPICreate(
        show_id=1,
        title="Test Show",
        enable_profile=True,
        use_downloads=False,
        use_dw_stream=True,
        preferred_format="format_audio_only",
        prefer_exact_match=False,
    )

    assert profile.video_output_mode is None


def test_video_rss_stream_profile_defaults_video_output_mode_to_audio_hls():
    from backend.api.models.rss_stream_profile import RssStreamProfileAPICreate
    from backend.types.stream_profile_types import RssVideoOutputMode

    profile = RssStreamProfileAPICreate(
        show_id=1,
        title="Test Show",
        enable_profile=True,
        use_downloads=False,
        use_dw_stream=True,
        preferred_format="format_1080p",
        prefer_exact_match=False,
    )

    assert profile.video_output_mode is RssVideoOutputMode.AUDIO_HLS


def test_audio_only_rss_stream_profile_rejects_video_output_mode():
    from backend.api.models.rss_stream_profile import RssStreamProfileAPICreate

    with pytest.raises(ValidationError, match="Audio-only Stream Profiles cannot have a video output mode"):
        RssStreamProfileAPICreate(
            show_id=1,
            title="Test Show",
            enable_profile=True,
            use_downloads=False,
            use_dw_stream=True,
            preferred_format="format_audio_only",
            prefer_exact_match=False,
            video_output_mode="audio_hls",
        )


def test_video_rss_stream_profile_requires_video_output_mode():
    from backend.api.models.rss_stream_profile import RssStreamProfileAPICreate

    with pytest.raises(ValidationError, match="Video Stream Profiles require a video output mode"):
        RssStreamProfileAPICreate(
            show_id=1,
            title="Test Show",
            enable_profile=True,
            use_downloads=False,
            use_dw_stream=True,
            preferred_format="format_1080p",
            prefer_exact_match=False,
            video_output_mode=None,
        )


def test_rss_stream_profile_database_video_output_mode_is_nullable():
    from backend.db.models import RssStreamProfile

    assert RssStreamProfile.__table__.c.video_output_mode.nullable is True


@pytest.fixture
def db_session():
    import backend.db.models  # noqa: F401
    from backend.db import Base

    engine = create_engine("sqlite+pysqlite:///:memory:")
    session = Session(engine)
    Base.metadata.create_all(engine)
    yield session
    session.close()
    engine.dispose()


def test_feed_items_respect_stream_profile_episode_types(db_session):
    from backend.api.endpoints.feeds.service import get_feed_items, get_media_for_episode
    from backend.db.models import Episode, RssStreamProfile, Season, Show
    from backend.types.show_types import EpisodeIdentifier, ShowType

    show = Show(
        uuid="show-uuid",
        slug="show",
        title="Show",
        description="Description",
        sharing_url="https://example.test/show",
        membership_level="FREE",
        type=ShowType.PODCAST.value,
        episode_identifier=EpisodeIdentifier.NUMBERED.value,
        author_name="Host",
        author_slug="host",
    )
    season = Season(show=show, index=1, slug="season-1", name="Season 1")
    normal = Episode(
        uuid="normal-uuid",
        type="episode",
        show=show,
        season=season,
        index=1,
        episode_identifier="ep.1",
        slug="normal",
        title="Normal",
        description="Normal episode",
        duration=1200,
        publish_status="published_final",
        sharing_url="https://example.test/normal",
        published_date=datetime(2026, 9, 1),
        is_no_show_today=False,
    )
    auxiliary = Episode(
        uuid="aux-uuid",
        type="episode",
        show=show,
        season=season,
        index=2,
        episode_identifier="aux.1",
        slug="auxiliary",
        title="Auxiliary",
        description="Auxiliary episode",
        duration=600,
        publish_status="published_final",
        sharing_url="https://example.test/auxiliary",
        published_date=datetime(2026, 8, 31),
        is_no_show_today=False,
    )
    profile = RssStreamProfile(
        show=show,
        enable_profile=True,
        token="token",
        use_downloads=False,
        use_dw_stream=True,
        preferred_format="format_audio_only",
        prefer_exact_match=False,
        ep_id_type_list=["ep"],
        feed_url="https://wireloft.test/feed.xml",
    )

    db_session.add_all([show, season, normal, auxiliary, profile])
    db_session.flush()

    assert [episode.slug for episode, _ in get_feed_items(db_session, profile)] == ["normal"]

    with pytest.raises(HTTPException) as exc_info:
        get_media_for_episode(db_session, profile, auxiliary.slug)
    assert exc_info.value.status_code == 404
