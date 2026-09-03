from types import SimpleNamespace


def test_seasonal_episode_number_renders_as_numeric_episode_number() -> None:
    from backend.utils.output_template import (
        SHOW_OUTPUT_TEMPLATE_FIELDS,
        episode_output_template_values,
        render_output_template,
    )

    episode = SimpleNamespace(
        show=SimpleNamespace(slug="chip-chilla", title="Chip Chilla"),
        season=SimpleNamespace(slug="season-1", name="Season 1", index=1),
        slug="chips-odyssey",
        title="Chip's Odyssey",
        episode_identifier="ep.S01E07",
        published_date=None,
    )
    values = episode_output_template_values(episode)

    assert values["episode_number"] == "7"
    assert render_output_template(
        "/downloads/Video/{{ show_title }}/Season {{ \"%02d\"|format(season_index|int) }}/"
        "{{ show_title }} - S{{ \"%02d\"|format(season_index|int) }}"
        "E{{ \"%02d\"|format(episode_number|int) }} - {{ title }}.ext",
        values,
        allowed_fields=SHOW_OUTPUT_TEMPLATE_FIELDS,
    ) == (
        "/downloads/Video/Chip Chilla/Season 01/"
        "Chip Chilla - S01E07 - Chip's Odyssey.ext"
    )


def test_seasonal_episode_extra_uses_parent_episode_number() -> None:
    from backend.utils.episode import episode_type_info

    assert episode_type_info("ep-extra.S03E12.2") == {
        "type": "ep-extra",
        "number": "12",
    }
