from __future__ import annotations

from backend.api.models.season import SeasonAPIRequestDetached
from backend.utils.season_ordering import order_initial_seasons


def _season(name: str, slug: str) -> SeasonAPIRequestDetached:
    return SeasonAPIRequestDetached(name=name, slug=slug)


def _slugs(seasons) -> list[str]:
    return [season.slug for season in seasons]


def test_initial_order_puts_unnumbered_seasons_before_sorted_numbered_seasons():
    seasons = [
        _season("Extras", "extras"),
        _season("Season 2", "debunked-season-2-season"),
        _season("Season 1", "debunked-season-1-season"),
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

    ordered = order_initial_seasons(seasons)

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

    ordered = order_initial_seasons(seasons)

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

    assert order_initial_seasons(seasons) == seasons
