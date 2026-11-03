from __future__ import annotations

from datetime import timedelta


def test_download_profile_cutoff_is_timezone_aware_utc():
    from backend.db.datetime_types import utc_datetime
    from task_manager.tasks.workers.download_profile_worker import _helpers

    cutoff = _helpers._utc_now() - timedelta(days=7)

    assert cutoff.utcoffset() == timedelta(0)
    assert utc_datetime(cutoff) == cutoff

