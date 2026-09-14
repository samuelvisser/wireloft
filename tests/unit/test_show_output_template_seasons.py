from __future__ import annotations

from datetime import datetime


def _show_with_interspersed_extra_seasons():
    from backend.db.models import Episode, Season, Show

    show = Show(
        uuid="show-extra-season-template",
        slug="extra-season-template",
        title="Extra Season Template",
        description=None,
        sharing_url="https://example.test/extra-season-template",
        membership_level="FREE",
        type="series",
        episode_identifier="numbered",
        author_name="Host",
        author_slug="host",
    )
    season_one = Season(show=show, index=1, slug="season-1", name="2022")
    extras_one = Season(show=show, index=2, slug="extras-1", name="Extras 1")
    season_two = Season(show=show, index=3, slug="season-2", name="2023")
    extras_two = Season(show=show, index=4, slug="extras-2", name="Bonus EXTRA Content")
    season_three = Season(show=show, index=5, slug="season-3", name="2024")

    def make_episode(*, suffix: str, season: Season, index: int, title: str) -> Episode:
        return Episode(
            uuid=f"episode-{suffix}",
            type="episode",
            show=show,
            season=season,
            index=index,
            episode_identifier=f"ep.{index}",
            slug=f"episode-{suffix}",
            title=title,
            description=None,
            duration=60,
            publish_status="published_final",
            sharing_url=f"https://example.test/episode-{suffix}",
            published_date=datetime(2026, 9, index, 12, 0, 0),
        )

    episodes = {
        "season_one": make_episode(suffix="season-one", season=season_one, index=1, title="Season One Episode"),
        "extras_one": make_episode(suffix="extras-one", season=extras_one, index=2, title="Extras One Episode"),
        "season_two": make_episode(suffix="season-two", season=season_two, index=3, title="Season Two Episode"),
        "extras_two": make_episode(suffix="extras-two", season=extras_two, index=4, title="Extras Two Episode"),
        "season_three": make_episode(suffix="season-three", season=season_three, index=5, title="Season Three Episode"),
    }
    return episodes


def test_episode_output_template_values_include_extra_season_metadata() -> None:
    from backend.utils.output_template import (
        SHOW_OUTPUT_TEMPLATE_FIELDS,
        episode_output_template_values,
    )

    episodes = _show_with_interspersed_extra_seasons()
    values = {
        key: episode_output_template_values(episode)
        for key, episode in episodes.items()
    }

    assert all(item.keys() == SHOW_OUTPUT_TEMPLATE_FIELDS for item in values.values())
    assert all(item["extra_seasons_count"] == "2" for item in values.values())

    assert values["season_one"]["is_extra_season"] == "0"
    assert values["extras_one"]["is_extra_season"] == "1"
    assert values["season_two"]["is_extra_season"] == "0"
    assert values["extras_two"]["is_extra_season"] == "1"
    assert values["season_three"]["is_extra_season"] == "0"


def test_normalized_season_index_ignores_only_earlier_extra_seasons() -> None:
    from backend.utils.output_template import episode_output_template_values

    episodes = _show_with_interspersed_extra_seasons()
    normalized = {
        key: episode_output_template_values(episode)["normalized_season_index"]
        for key, episode in episodes.items()
    }

    assert normalized == {
        "season_one": "1",
        "extras_one": "0",
        "season_two": "2",
        "extras_two": "0",
        "season_three": "3",
    }


def test_normalized_season_index_is_numeric_inside_jinja() -> None:
    from backend.utils.output_template import (
        SHOW_OUTPUT_TEMPLATE_FIELDS,
        episode_output_template_values,
        render_output_template,
    )

    episodes = _show_with_interspersed_extra_seasons()
    template = (
        "/downloads/Season {{ \"%02d\"|format(normalized_season_index) }}/{{ title }}.ext"
    )

    rendered = {
        key: render_output_template(
            template,
            episode_output_template_values(episode),
            allowed_fields=SHOW_OUTPUT_TEMPLATE_FIELDS,
        )
        for key, episode in episodes.items()
    }

    assert rendered["season_one"] == "/downloads/Season 01/Season One Episode.ext"
    assert rendered["extras_one"] == "/downloads/Season 00/Extras One Episode.ext"
    assert rendered["season_two"] == "/downloads/Season 02/Season Two Episode.ext"
    assert rendered["extras_two"] == "/downloads/Season 00/Extras Two Episode.ext"
    assert rendered["season_three"] == "/downloads/Season 03/Season Three Episode.ext"
