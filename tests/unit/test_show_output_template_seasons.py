from __future__ import annotations

from datetime import datetime


def _show_with_extra_seasons():
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
    extras = Season(show=show, index=1, slug="extras", name="Extras")
    bonus_extras = Season(show=show, index=2, slug="bonus-extras", name="Bonus EXTRA Content")
    season_one = Season(show=show, index=3, slug="season-1", name="Season 1")

    extra_episode = Episode(
        uuid="extra-episode",
        type="episode",
        show=show,
        season=extras,
        index=1,
        episode_identifier="ep-extra.1",
        slug="extra-episode",
        title="Extra Episode",
        description=None,
        duration=60,
        publish_status="published_final",
        sharing_url="https://example.test/extra-episode",
        published_date=datetime(2026, 9, 1, 12, 0, 0),
    )
    regular_episode = Episode(
        uuid="regular-episode",
        type="episode",
        show=show,
        season=season_one,
        index=2,
        episode_identifier="ep.1",
        slug="regular-episode",
        title="Regular Episode",
        description=None,
        duration=60,
        publish_status="published_final",
        sharing_url="https://example.test/regular-episode",
        published_date=datetime(2026, 9, 2, 12, 0, 0),
    )

    # Keep the second extras season referenced so SQLAlchemy does not consider it
    # an unused construction detail in future model refactors.
    assert bonus_extras.show is show
    return extra_episode, regular_episode


def test_episode_output_template_values_include_extra_season_metadata() -> None:
    from backend.utils.output_template import (
        SHOW_OUTPUT_TEMPLATE_FIELDS,
        episode_output_template_values,
    )

    extra_episode, regular_episode = _show_with_extra_seasons()

    extra_values = episode_output_template_values(extra_episode)
    regular_values = episode_output_template_values(regular_episode)

    assert extra_values.keys() == regular_values.keys() == SHOW_OUTPUT_TEMPLATE_FIELDS
    assert extra_values["extra_seasons_count"] == "2"
    assert regular_values["extra_seasons_count"] == "2"
    assert extra_values["is_extra_season"] == "1"
    assert regular_values["is_extra_season"] == "0"


def test_extra_season_flag_and_count_are_numeric_inside_jinja() -> None:
    from backend.utils.output_template import (
        SHOW_OUTPUT_TEMPLATE_FIELDS,
        episode_output_template_values,
        render_output_template,
    )

    extra_episode, regular_episode = _show_with_extra_seasons()
    template = (
        "{% set plex_season = 0 if is_extra_season else (season_index|int) - extra_seasons_count %}"
        "/downloads/Season {{ \"%02d\"|format(plex_season) }}/{{ title }}.ext"
    )

    extra_path = render_output_template(
        template,
        episode_output_template_values(extra_episode),
        allowed_fields=SHOW_OUTPUT_TEMPLATE_FIELDS,
    )
    regular_path = render_output_template(
        template,
        episode_output_template_values(regular_episode),
        allowed_fields=SHOW_OUTPUT_TEMPLATE_FIELDS,
    )

    assert extra_path == "/downloads/Season 00/Extra Episode.ext"
    assert regular_path == "/downloads/Season 01/Regular Episode.ext"
