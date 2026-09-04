from __future__ import annotations

from backend.api.models.season import SeasonAPIRequestDetached
from backend.utils.season_ordering import order_initial_seasons
from dailywire_api.records import DwSeasonRecord
from task_manager.tasks.helpers.seasons import (
    order_initial_dw_seasons,
    select_dw_seasons_to_create,
)


def _season(name: str, slug: str) -> DwSeasonRecord:
    return DwSeasonRecord(id=slug, name=name, slug=slug)


def _slugs(seasons) -> list[str]:
    return [season.slug for season in seasons]


def test_initial_order_puts_unnumbered_seasons_before_sorted_numbered_seasons():
    seasons = [
        _season("Extras", "extras"),
        _season("Season 2", "debunked-season-2-season"),
        _season("Season 1", "debunked-season-1-season"),
    ]

    ordered = order_initial_dw_seasons(seasons)

    assert _slugs(ordered) == [
        "extras",
        "debunked-season-1-season",
        "debunked-season-2-season",
    ]


def test_bundle_seasons_use_the_same_initial_ordering_before_indices_are_assigned():
    seasons = [
        SeasonAPIRequestDetached(name="Extras", slug="extras"),
        SeasonAPIRequestDetached(name="Season 2", slug="debunked-season-2-season"),
        SeasonAPIRequestDetached(name="Season 1", slug="debunked-season-1-season"),
    ]

    ordered = order_initial_seasons(seasons)

    assert _slugs(ordered) == [
        "extras",
        "debunked-season-1-season",
        "debunked-season-2-season",
    ]


def test_initial_order_preserves_api_order_for_multiple_unnumbered_seasons():
    seasons = [
        _season("Extras", "extras"),
        _season("Specials", "specials"),
        _season("Season 3", "example-season-3-season"),
        _season("Season 1", "example-season-1-season"),
        _season("Season 2", "example-season-2-season"),
    ]

    ordered = order_initial_dw_seasons(seasons)

    assert _slugs(ordered) == [
        "extras",
        "specials",
        "example-season-1-season",
        "example-season-2-season",
        "example-season-3-season",
    ]


def test_initial_order_sorts_year_seasons_in_both_dailywire_slug_formats():
    seasons = [
        _season("Extras", "extras"),
        _season("2026", "the-andrew-klavan-show-2026-season"),
        _season("2024", "the-andrew-klavan-show-2024-season"),
        _season("2025", "the-andrew-klavan-show-season-2025"),
        _season("2023", "the-andrew-klavan-show-season-2023"),
    ]

    ordered = order_initial_dw_seasons(seasons)

    assert [season.name for season in ordered] == [
        "Extras",
        "2023",
        "2024",
        "2025",
        "2026",
    ]


def test_initial_order_leaves_fully_unstructured_api_order_unchanged():
    seasons = [
        _season("Bonus", "bonus"),
        _season("Extras", "extras"),
        _season("Archive", "archive"),
    ]

    assert order_initial_dw_seasons(seasons) == seasons


def test_subsequent_discovery_only_appends_unknown_seasons_without_reordering():
    seasons = [
        _season("Extras", "extras"),
        _season("Season 4", "example-season-4-season"),
        _season("Season 3", "example-season-3-season"),
        _season("Season 2", "example-season-2-season"),
        _season("Season 1", "example-season-1-season"),
    ]

    new_seasons = select_dw_seasons_to_create(
        existing_season_slugs={
            "extras",
            "example-season-1-season",
            "example-season-2-season",
        },
        seasons=seasons,
    )

    # This intentionally preserves Daily Wire discovery order after initial index.
    # Existing indices are immutable and the worker simply assigns the next index.
    assert _slugs(new_seasons) == [
        "example-season-4-season",
        "example-season-3-season",
    ]
