from __future__ import annotations

from datetime import datetime, timedelta, timezone


class _EpisodeStub:
    def __init__(self):
        self.metadata: dict[str, str | None] = {}

    def get_meta(self, key: str) -> str | None:
        return self.metadata.get(key)

    def set_meta(self, key: str, value: str | None):
        self.metadata[key] = value


def test_monitor_timing_uses_first_trusted_exit_from_live():
    from backend.types.episode_types import EpisodePublishStatus
    from task_manager.tasks.helpers.episodes.trusted_publication_timing import (
        TRUSTED_LIVE_ENDED_META_KEY,
        track_monitor_publication_timing,
    )

    episode = _EpisodeStub()
    went_live = datetime(2026, 10, 2, 8, 0, tzinfo=timezone.utc)
    live_ended = went_live + timedelta(hours=1)
    became_final = live_ended + timedelta(minutes=2)

    # Seeing the transition into LIVE is not enough; discovery may have found
    # the episode only at this poll.
    track_monitor_publication_timing(
        episode,
        old_status=EpisodePublishStatus.SCHEDULED.value,
        new_status=EpisodePublishStatus.LIVE,
        observed_at=went_live,
    )
    assert episode.get_meta(TRUSTED_LIVE_ENDED_META_KEY) is None

    # A subsequent LIVE -> LIVE poll proves this monitor is actively following
    # the episode during the live phase.
    track_monitor_publication_timing(
        episode,
        old_status=EpisodePublishStatus.LIVE.value,
        new_status=EpisodePublishStatus.LIVE,
        observed_at=went_live + timedelta(minutes=2),
    )
    track_monitor_publication_timing(
        episode,
        old_status=EpisodePublishStatus.LIVE.value,
        new_status=EpisodePublishStatus.DW_PROCESSING,
        observed_at=live_ended,
    )

    marker = episode.get_meta(TRUSTED_LIVE_ENDED_META_KEY)
    assert marker == f"monitor:live_ended:{live_ended.isoformat()}"

    track_monitor_publication_timing(
        episode,
        old_status=EpisodePublishStatus.DW_PROCESSING.value,
        new_status=EpisodePublishStatus.PUBLISHED_FINAL,
        observed_at=became_final,
    )
    assert episode.get_meta(TRUSTED_LIVE_ENDED_META_KEY) == marker

    # A later LIVE regression cannot reuse proof from the first live phase.
    track_monitor_publication_timing(
        episode,
        old_status=EpisodePublishStatus.PUBLISHED_FINAL.value,
        new_status=EpisodePublishStatus.LIVE,
        observed_at=became_final + timedelta(minutes=1),
    )
    track_monitor_publication_timing(
        episode,
        old_status=EpisodePublishStatus.LIVE.value,
        new_status=EpisodePublishStatus.PUBLISHED_FINAL,
        observed_at=became_final + timedelta(minutes=2),
    )
    assert episode.get_meta(TRUSTED_LIVE_ENDED_META_KEY) == marker


def test_monitor_timing_does_not_trust_first_observed_live_transition():
    from backend.types.episode_types import EpisodePublishStatus
    from task_manager.tasks.helpers.episodes.trusted_publication_timing import (
        TRUSTED_LIVE_ENDED_META_KEY,
        track_monitor_publication_timing,
    )

    episode = _EpisodeStub()
    went_live = datetime(2026, 10, 2, 8, 0, tzinfo=timezone.utc)

    track_monitor_publication_timing(
        episode,
        old_status=EpisodePublishStatus.DELAYED.value,
        new_status=EpisodePublishStatus.LIVE,
        observed_at=went_live,
    )
    track_monitor_publication_timing(
        episode,
        old_status=EpisodePublishStatus.LIVE.value,
        new_status=EpisodePublishStatus.PUBLISHED_FINAL,
        observed_at=went_live + timedelta(minutes=2),
    )

    assert episode.get_meta(TRUSTED_LIVE_ENDED_META_KEY) is None


def test_monitor_timing_falls_back_when_live_entry_was_not_observed():
    from backend.types.episode_types import EpisodePublishStatus
    from task_manager.tasks.helpers.episodes.trusted_publication_timing import (
        TRUSTED_LIVE_ENDED_META_KEY,
        track_monitor_publication_timing,
    )

    episode = _EpisodeStub()

    track_monitor_publication_timing(
        episode,
        old_status=EpisodePublishStatus.LIVE.value,
        new_status=EpisodePublishStatus.PUBLISHED_FINAL,
        observed_at=datetime(2026, 10, 2, 9, 0, tzinfo=timezone.utc),
    )

    assert episode.get_meta(TRUSTED_LIVE_ENDED_META_KEY) is None


def test_monitor_timing_does_not_trust_live_state_from_previous_process():
    from backend.types.episode_types import EpisodePublishStatus
    from task_manager.tasks.helpers.episodes.trusted_publication_timing import (
        TRUSTED_LIVE_ENDED_META_KEY,
        MONITOR_LIVE_SESSION_META_KEY,
        track_monitor_publication_timing,
    )

    episode = _EpisodeStub()
    episode.set_meta(
        MONITOR_LIVE_SESSION_META_KEY,
        "previous-process:2026-10-02T08:00:00+00:00",
    )

    track_monitor_publication_timing(
        episode,
        old_status=EpisodePublishStatus.LIVE.value,
        new_status=EpisodePublishStatus.PUBLISHED_WITH_COUNTDOWN,
        observed_at=datetime(2026, 10, 2, 9, 0, tzinfo=timezone.utc),
    )

    assert episode.get_meta(TRUSTED_LIVE_ENDED_META_KEY) is None
