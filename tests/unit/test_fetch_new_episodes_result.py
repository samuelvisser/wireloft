from __future__ import annotations


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
