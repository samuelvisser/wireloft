from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _episode_fixture():
    import backend.db.models  # noqa: F401
    from backend.db import Base
    from backend.db.models import Episode, Season, Show
    from backend.types.show_types import EpisodeIdentifier, ShowType
    from backend.utils.helpers import generate_uuid

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    show = Show(
        uuid="timing-show-uuid",
        slug="timing-show",
        title="Timing Show",
        description=None,
        sharing_url="https://example.test/show",
        membership_level="FREE",
        type=ShowType.PODCAST.value,
        episode_identifier=EpisodeIdentifier.NUMBERED.value,
        author_name="Host",
        author_slug="host",
    )
    season = Season(show=show, index=1, slug="season-1", name="One")
    episode = Episode(
        uuid=generate_uuid(),
        type="episode",
        show=show,
        season=season,
        index=1,
        episode_identifier="ep.1",
        slug="timing-episode",
        title="Timing Episode",
        duration=3600.0,
        publish_status="published_final",
        sharing_url="https://example.test/episode",
        published_date=datetime(2026, 10, 2, 8, tzinfo=timezone.utc),
    )
    session.add_all([show, season, episode])
    session.commit()
    return engine, session, episode


def test_safe_publication_timestamps_are_none_without_safe_evidence():
    from backend.utils.episode_publication_timing import (
        TRUSTED_LIVE_ENDED_META_KEY,
        TRUSTED_PUBLISHED_FINAL_META_KEY,
    )

    engine, session, episode = _episode_fixture()
    try:
        assert episode.safe_live_ended is None
        assert episode.safe_published_final is None

        episode.set_meta(TRUSTED_LIVE_ENDED_META_KEY, "not-trusted")
        episode.set_meta(TRUSTED_PUBLISHED_FINAL_META_KEY, "not-trusted")
        session.flush()

        assert episode.safe_live_ended is None
        assert episode.safe_published_final is None
    finally:
        session.close()
        engine.dispose()


def test_monitor_records_safe_live_end_and_published_final_separately():
    from backend.types.episode_types import EpisodePublishStatus
    from task_manager.tasks.helpers.episodes.trusted_publication_timing import (
        track_monitor_publication_timing,
    )

    engine, session, episode = _episode_fixture()
    try:
        live_poll = datetime(2026, 10, 2, 8, 30, tzinfo=timezone.utc)
        live_ended = live_poll + timedelta(minutes=30)
        published_final = live_ended + timedelta(minutes=4)

        track_monitor_publication_timing(
            episode,
            old_status=EpisodePublishStatus.LIVE.value,
            new_status=EpisodePublishStatus.LIVE,
            observed_at=live_poll,
        )
        assert episode.safe_live_ended is None
        assert episode.safe_published_final is None

        track_monitor_publication_timing(
            episode,
            old_status=EpisodePublishStatus.LIVE.value,
            new_status=EpisodePublishStatus.PUBLISHED_WITH_COUNTDOWN,
            observed_at=live_ended,
        )
        assert episode.safe_live_ended == live_ended
        assert episode.safe_published_final is None

        track_monitor_publication_timing(
            episode,
            old_status=EpisodePublishStatus.PUBLISHED_WITH_COUNTDOWN.value,
            new_status=EpisodePublishStatus.PUBLISHED_FINAL,
            observed_at=published_final,
        )
        assert episode.safe_live_ended == live_ended
        assert episode.safe_published_final == published_final
    finally:
        session.close()
        engine.dispose()


def test_new_live_cycle_invalidates_previous_safe_timestamps():
    from backend.types.episode_types import EpisodePublishStatus
    from backend.utils.episode_publication_timing import (
        TRUSTED_LIVE_ENDED_META_KEY,
        TRUSTED_PUBLISHED_FINAL_META_KEY,
        encode_safe_live_ended,
        encode_safe_published_final,
    )
    from task_manager.tasks.helpers.episodes.trusted_publication_timing import (
        track_monitor_publication_timing,
    )

    engine, session, episode = _episode_fixture()
    try:
        previous_live_end = datetime(2026, 10, 2, 8, 30, tzinfo=timezone.utc)
        previous_final = datetime(2026, 10, 2, 8, 35, tzinfo=timezone.utc)
        episode.set_meta(
            TRUSTED_LIVE_ENDED_META_KEY,
            encode_safe_live_ended(previous_live_end),
        )
        episode.set_meta(
            TRUSTED_PUBLISHED_FINAL_META_KEY,
            encode_safe_published_final(previous_final),
        )
        assert episode.safe_live_ended == previous_live_end
        assert episode.safe_published_final == previous_final

        track_monitor_publication_timing(
            episode,
            old_status=EpisodePublishStatus.DELAYED.value,
            new_status=EpisodePublishStatus.LIVE,
            observed_at=datetime(2026, 10, 2, 10, tzinfo=timezone.utc),
        )

        assert episode.safe_live_ended is None
        assert episode.safe_published_final is None
    finally:
        session.close()
        engine.dispose()


def test_safe_published_final_requires_prior_poll_in_current_process():
    from backend.types.episode_types import EpisodePublishStatus
    from task_manager.tasks.helpers.episodes.trusted_publication_timing import (
        MONITOR_PENDING_SESSION_META_KEY,
        track_monitor_publication_timing,
    )

    engine, session, episode = _episode_fixture()
    try:
        episode.set_meta(
            MONITOR_PENDING_SESSION_META_KEY,
            "previous-process:2026-10-02T08:00:00+00:00",
        )
        track_monitor_publication_timing(
            episode,
            old_status=EpisodePublishStatus.DW_PROCESSING.value,
            new_status=EpisodePublishStatus.PUBLISHED_FINAL,
            observed_at=datetime(2026, 10, 2, 9, tzinfo=timezone.utc),
        )

        assert episode.safe_published_final is None
    finally:
        session.close()
        engine.dispose()
