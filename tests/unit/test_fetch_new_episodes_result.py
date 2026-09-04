from __future__ import annotations

import json


def test_fetch_new_episodes_result_builds_structured_summary():
    from task_manager.tasks.workers.fetch_new_episodes.service import (
        FetchNewEpisodesResult,
        ShowEpisodeScanResult,
    )

    result = FetchNewEpisodesResult(shows=(
        ShowEpisodeScanResult(
            show_id=1,
            show_slug="first-show",
            show_title="First Show",
            episodes_found=2,
        ),
        ShowEpisodeScanResult(
            show_id=2,
            show_slug="second-show",
            show_title="Second Show",
            episodes_found=1,
        ),
    ))

    assert result.episodes_found == 3
    assert result.shows_scanned == 2
    assert result.summary() == "Episode scan finished for 2 shows: 3 new episodes found"
    assert result.as_data() == {
        "episodes_found": 3,
        "shows_scanned": 2,
        "shows": [
            {
                "show_id": 1,
                "show_slug": "first-show",
                "show_title": "First Show",
                "episodes_found": 2,
            },
            {
                "show_id": 2,
                "show_slug": "second-show",
                "show_title": "Second Show",
                "episodes_found": 1,
            },
        ],
    }


def test_sync_logger_keeps_only_latest_entries():
    from task_manager.tasks.workers.fetch_new_episodes.sync_logger import (
        SYNC_LOG_LIMIT,
        SYNC_LOG_META_KEY,
        append_sync_log,
    )

    class FakeShow:
        def __init__(self):
            self.meta: dict[str, str] = {}

        def get_meta(self, key: str):
            return self.meta.get(key)

        def set_meta(self, key: str, value: str):
            self.meta[key] = value

    show = FakeShow()
    for found in range(SYNC_LOG_LIMIT + 2):
        append_sync_log(
            show,  # type: ignore[arg-type]
            episodes_found=found,
            status="completed",
        )

    history = json.loads(show.meta[SYNC_LOG_META_KEY])
    assert len(history) == SYNC_LOG_LIMIT
    assert history[0]["episodes_found"] == SYNC_LOG_LIMIT + 1
    assert history[-1]["episodes_found"] == 2
    assert all(entry["status"] == "completed" for entry in history)


def test_sync_logger_records_retry_state_for_failures():
    from task_manager.tasks.workers.fetch_new_episodes.sync_logger import (
        SYNC_LOG_META_KEY,
        append_sync_log,
    )

    class FakeShow:
        def __init__(self):
            self.meta: dict[str, str] = {}

        def get_meta(self, key: str):
            return self.meta.get(key)

        def set_meta(self, key: str, value: str):
            self.meta[key] = value

    show = FakeShow()
    append_sync_log(
        show,  # type: ignore[arg-type]
        episodes_found=0,
        status="failed",
        will_retry=True,
    )

    [entry] = json.loads(show.meta[SYNC_LOG_META_KEY])
    assert entry["episodes_found"] == 0
    assert entry["status"] == "failed"
    assert entry["will_retry"] is True
    assert isinstance(entry["synced_at"], str)
