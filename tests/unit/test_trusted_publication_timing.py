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


def test_publication_timestamps_are_none_without_valid_evidence():
    from backend.utils.episode_publication_timing import (
        LAST_KNOWN_PENDING_META_KEY,
        RECORDED_PUBLISHED_FINAL_META_KEY,
        TRUSTED_LIVE_ENDED_META_KEY,
        TRUSTED_PUBLISHED_FINAL_META_KEY,
    )

    engine, session, episode = _episode_fixture()
    try:
        assert episode.safe_live_ended is None
        assert episode.safe_published_final is None
        assert episode.last_known_pending is None
        assert episode.recorded_published_final is None

        episode.set_meta(TRUSTED_LIVE_ENDED_META_KEY, "not-trusted")
        episode.set_meta(TRUSTED_PUBLISHED_FINAL_META_KEY, "not-trusted")
        episode.set_meta(LAST_KNOWN_PENDING_META_KEY, "not-a-timestamp")
        episode.set_meta(RECORDED_PUBLISHED_FINAL_META_KEY, "not-a-timestamp")
        session.flush()

        assert episode.safe_live_ended is None
        assert episode.safe_published_final is None
        assert episode.last_known_pending is None
        assert episode.recorded_published_final is None
    finally:
        session.close()
        engine.dispose()


def test_monitor_records_safe_live_end_and_published_final_separately():
    from backend.types.episode_types import EpisodePublishStatus
    from backend.utils.episode_publication_timing import best_effort_published_date
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
        assert episode.last_known_pending is None
        assert episode.recorded_published_final == published_final
        assert best_effort_published_date(episode) == published_final
    finally:
        session.close()
        engine.dispose()


def test_new_live_cycle_invalidates_previous_publication_timing():
    from backend.types.episode_types import EpisodePublishStatus
    from backend.utils.episode_publication_timing import (
        LAST_KNOWN_PENDING_META_KEY,
        RECORDED_PUBLISHED_FINAL_META_KEY,
        TRUSTED_LIVE_ENDED_META_KEY,
        TRUSTED_PUBLISHED_FINAL_META_KEY,
        encode_last_known_pending,
        encode_recorded_published_final,
        encode_safe_live_ended,
        encode_safe_published_final,
    )
    from task_manager.tasks.helpers.episodes.trusted_publication_timing import (
        track_monitor_publication_timing,
    )

    engine, session, episode = _episode_fixture()
    try:
        previous_live_end = datetime(2026, 10, 2, 8, 30, tzinfo=timezone.utc)
        previous_pending = datetime(2026, 10, 2, 8, 34, tzinfo=timezone.utc)
        previous_final = datetime(2026, 10, 2, 8, 35, tzinfo=timezone.utc)
        episode.set_meta(
            TRUSTED_LIVE_ENDED_META_KEY,
            encode_safe_live_ended(previous_live_end),
        )
        episode.set_meta(
            TRUSTED_PUBLISHED_FINAL_META_KEY,
            encode_safe_published_final(previous_final),
        )
        episode.set_meta(
            LAST_KNOWN_PENDING_META_KEY,
            encode_last_known_pending(previous_pending),
        )
        episode.set_meta(
            RECORDED_PUBLISHED_FINAL_META_KEY,
            encode_recorded_published_final(previous_final),
        )

        track_monitor_publication_timing(
            episode,
            old_status=EpisodePublishStatus.DELAYED.value,
            new_status=EpisodePublishStatus.LIVE,
            observed_at=datetime(2026, 10, 2, 10, tzinfo=timezone.utc),
        )

        assert episode.safe_live_ended is None
        assert episode.safe_published_final is None
        assert episode.last_known_pending is None
        assert episode.recorded_published_final is None
    finally:
        session.close()
        engine.dispose()


def test_repeated_pending_observation_does_not_start_a_new_publication_lifecycle():
    from backend.types.episode_types import EpisodePublishStatus
    from backend.utils.episode_publication_timing import (
        RECORDED_PUBLISHED_FINAL_META_KEY,
        encode_recorded_published_final,
        record_publication_lifecycle_observation,
    )

    engine, session, episode = _episode_fixture()
    try:
        recorded_final = datetime(2026, 10, 2, 8, 35, tzinfo=timezone.utc)
        episode.set_meta(
            RECORDED_PUBLISHED_FINAL_META_KEY,
            encode_recorded_published_final(recorded_final),
        )

        record_publication_lifecycle_observation(
            episode,
            old_status=EpisodePublishStatus.SCHEDULED.value,
            new_status=EpisodePublishStatus.SCHEDULED,
            observed_at=datetime(2026, 10, 2, 10, tzinfo=timezone.utc),
        )

        assert episode.recorded_published_final == recorded_final
    finally:
        session.close()
        engine.dispose()


def test_new_lifecycle_does_not_reuse_prior_live_monitor_evidence():
    from backend.types.episode_types import EpisodePublishStatus
    from task_manager.tasks.helpers.episodes.trusted_publication_timing import (
        track_monitor_publication_timing,
    )

    engine, session, episode = _episode_fixture()
    try:
        track_monitor_publication_timing(
            episode,
            old_status=EpisodePublishStatus.LIVE.value,
            new_status=EpisodePublishStatus.LIVE,
            observed_at=datetime(2026, 10, 2, 8, tzinfo=timezone.utc),
        )
        assert episode.safe_live_ended is None

        track_monitor_publication_timing(
            episode,
            old_status=EpisodePublishStatus.PUBLISHED_FINAL.value,
            new_status=EpisodePublishStatus.LIVE,
            observed_at=datetime(2026, 10, 2, 10, tzinfo=timezone.utc),
        )
        track_monitor_publication_timing(
            episode,
            old_status=EpisodePublishStatus.LIVE.value,
            new_status=EpisodePublishStatus.PUBLISHED_WITH_COUNTDOWN,
            observed_at=datetime(2026, 10, 2, 10, 1, tzinfo=timezone.utc),
        )

        assert episode.safe_live_ended is None
    finally:
        session.close()
        engine.dispose()


def test_restart_materializes_last_known_pending_without_claiming_safe_final():
    from backend.types.episode_types import EpisodePublishStatus
    from backend.utils.episode_publication_timing import best_effort_published_date
    from task_manager.tasks.helpers.episodes.trusted_publication_timing import (
        MONITOR_PENDING_SESSION_META_KEY,
        track_monitor_publication_timing,
    )

    engine, session, episode = _episode_fixture()
    try:
        last_pending = datetime(2026, 10, 2, 8, 30, tzinfo=timezone.utc)
        first_final_observation = datetime(2026, 10, 2, 9, tzinfo=timezone.utc)
        episode.set_meta(
            MONITOR_PENDING_SESSION_META_KEY,
            f"previous-process:{last_pending.isoformat()}",
        )

        track_monitor_publication_timing(
            episode,
            old_status=EpisodePublishStatus.DW_PROCESSING.value,
            new_status=EpisodePublishStatus.PUBLISHED_FINAL,
            observed_at=first_final_observation,
        )

        assert episode.safe_published_final is None
        assert episode.last_known_pending == last_pending
        assert episode.recorded_published_final == first_final_observation
        assert best_effort_published_date(episode) == last_pending
        assert episode.get_meta(MONITOR_PENDING_SESSION_META_KEY).startswith("consumed:")
    finally:
        session.close()
        engine.dispose()


def test_best_effort_uses_later_dailywire_date_than_interrupted_pending_observation():
    from backend.types.episode_types import EpisodePublishStatus
    from backend.utils.episode_publication_timing import best_effort_published_date
    from task_manager.tasks.helpers.episodes.trusted_publication_timing import (
        MONITOR_PENDING_SESSION_META_KEY,
        track_monitor_publication_timing,
    )

    engine, session, episode = _episode_fixture()
    try:
        last_pending = datetime(2026, 10, 2, 7, 45, tzinfo=timezone.utc)
        first_final_observation = datetime(2026, 10, 2, 9, tzinfo=timezone.utc)
        episode.set_meta(
            MONITOR_PENDING_SESSION_META_KEY,
            f"previous-process:{last_pending.isoformat()}",
        )

        track_monitor_publication_timing(
            episode,
            old_status=EpisodePublishStatus.DW_PROCESSING.value,
            new_status=EpisodePublishStatus.PUBLISHED_FINAL,
            observed_at=first_final_observation,
        )

        assert episode.published_date == datetime(2026, 10, 2, 8, tzinfo=timezone.utc)
        assert episode.last_known_pending == last_pending
        assert best_effort_published_date(episode) == episode.published_date
    finally:
        session.close()
        engine.dispose()


def test_episode_lifecycle_records_final_without_monitor_continuity():
    from backend.types.episode_types import EpisodePublishStatus
    from task_manager.tasks.helpers.episodes.events import queue_episode_status_events

    engine, session, episode = _episode_fixture()
    try:
        episode.publish_status = EpisodePublishStatus.PUBLISHED_FINAL.value
        queue_episode_status_events(
            session,
            episode=episode,
            show=episode.show,
            old_status=EpisodePublishStatus.DW_PROCESSING.value,
            new_status=EpisodePublishStatus.PUBLISHED_FINAL,
            was_created=False,
        )

        assert episode.safe_published_final is None
        assert episode.last_known_pending is None
        assert episode.recorded_published_final is not None
    finally:
        session.rollback()
        session.close()
        engine.dispose()


def test_recorded_final_is_an_audit_fact_not_a_best_effort_fallback():
    from backend.utils.episode_publication_timing import (
        best_effort_published_date,
        record_published_final_observation,
    )

    engine, session, episode = _episode_fixture()
    try:
        observed_final = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
        assert record_published_final_observation(
            episode,
            observed_at=observed_final,
        ) == observed_final
        assert episode.recorded_published_final == observed_final
        assert episode.safe_published_final is None
        assert episode.last_known_pending is None
        assert best_effort_published_date(episode) == episode.published_date

        later_observation = observed_final + timedelta(hours=1)
        assert record_published_final_observation(
            episode,
            observed_at=later_observation,
        ) == observed_final
        assert episode.recorded_published_final == observed_final
    finally:
        session.close()
        engine.dispose()
