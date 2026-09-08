from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace


def test_download_profile_cutoff_is_timezone_aware_utc():
    from backend.db.datetime_types import utc_datetime
    from task_manager.tasks.workers.download_profile_worker import _helpers

    cutoff = _helpers._utc_now() - timedelta(days=7)

    assert cutoff.utcoffset() == timedelta(0)
    assert utc_datetime(cutoff) == cutoff


def test_download_profile_recency_fallback_is_timezone_aware():
    from task_manager.tasks.workers.download_profile_worker._helpers import _episode_recency_key

    episode = SimpleNamespace(published_date=None, went_live_date=None, id=1)
    timestamp, episode_id = _episode_recency_key(episode)

    assert timestamp.utcoffset() == timedelta(0)
    assert episode_id == 1
