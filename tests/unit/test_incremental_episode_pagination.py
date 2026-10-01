from __future__ import annotations

from datetime import datetime, timezone


def _record(slug: str):
    from dailywire_api.records import DwEpisodeRecord

    return DwEpisodeRecord(
        dw_id=f"remote-{slug}",
        slug=slug,
        title=slug,
        description=None,
        duration=60,
        episode_number="1.00",
        display_episode_number="",
        background_image_path=None,
        sharing_url=f"https://example.test/{slug}",
        publish_status="PUBLISHED",
        is_downloadable=True,
        is_trailer=False,
        available_for=[],
        thumbnail_landscape_path=None,
        thumbnail_portrait_path=None,
        thumbnail_square_path=None,
        published_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        scheduled_date=None,
    )


def test_incremental_fetch_stops_when_known_cursor_is_seen():
    from dailywire_api.dw_api.client import (
        ByNextPage,
        ByShowSeason,
        EpisodesPaginatedResult,
    )
    from task_manager.tasks.helpers.episodes.mapper import fetch_episodes_until_slug

    pages = {
        "initial": EpisodesPaginatedResult(
            [_record("new-2"), _record("new-1")],
            "https://example.test/page-2",
            True,
        ),
        "https://example.test/page-2": EpisodesPaginatedResult(
            [_record("known-cursor"), _record("old-1")],
            "https://example.test/page-3",
            True,
        ),
        "https://example.test/page-3": EpisodesPaginatedResult(
            [_record("old-2")],
            None,
            False,
        ),
    }
    calls: list[str] = []

    class FakeClient:
        def get_episodes_paginated(self, _show_slug, selector):
            if isinstance(selector, ByShowSeason):
                calls.append("initial")
                return pages["initial"]
            assert isinstance(selector, ByNextPage)
            calls.append(selector.next_page_url)
            return pages[selector.next_page_url]

    items = fetch_episodes_until_slug(
        FakeClient(),
        "show",
        ByShowSeason(
            season_dw_id="season",
            membership_plan="FREE",
            page_size=50,
            order_by="CreatedAt_DESC",
        ),
        stop_slug="known-cursor",
    )

    assert [item.slug for item in items] == [
        "new-2",
        "new-1",
        "known-cursor",
        "old-1",
    ]
    assert calls == ["initial", "https://example.test/page-2"]


def test_incremental_fetch_falls_back_to_end_when_cursor_disappeared():
    from dailywire_api.dw_api.client import (
        ByNextPage,
        ByShowSeason,
        EpisodesPaginatedResult,
    )
    from task_manager.tasks.helpers.episodes.mapper import fetch_episodes_until_slug

    pages = {
        "initial": EpisodesPaginatedResult(
            [_record("new")],
            "https://example.test/page-2",
            True,
        ),
        "https://example.test/page-2": EpisodesPaginatedResult(
            [_record("old")],
            None,
            False,
        ),
    }
    calls: list[str] = []

    class FakeClient:
        def get_episodes_paginated(self, _show_slug, selector):
            if isinstance(selector, ByShowSeason):
                calls.append("initial")
                return pages["initial"]
            assert isinstance(selector, ByNextPage)
            calls.append(selector.next_page_url)
            return pages[selector.next_page_url]

    items = fetch_episodes_until_slug(
        FakeClient(),
        "show",
        ByShowSeason(
            season_dw_id="season",
            membership_plan="FREE",
            page_size=50,
            order_by="CreatedAt_DESC",
        ),
        stop_slug="missing-cursor",
    )

    assert [item.slug for item in items] == ["new", "old"]
    assert calls == ["initial", "https://example.test/page-2"]
