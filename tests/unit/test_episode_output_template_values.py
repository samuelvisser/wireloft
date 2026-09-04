from types import SimpleNamespace


def _episode(identifier: str):
    return SimpleNamespace(
        show=SimpleNamespace(slug="chip-chilla", title="Chip Chilla"),
        season=SimpleNamespace(slug="season-1", name="Season 1", index=1),
        slug="chips-odyssey",
        title="Chip's Odyssey",
        episode_identifier=identifier,
        published_date=None,
    )


def test_seasonal_episode_number_renders_as_numeric_episode_number() -> None:
    from backend.utils.output_template import (
        SHOW_OUTPUT_TEMPLATE_FIELDS,
        episode_output_template_values,
        render_output_template,
    )

    values = episode_output_template_values(_episode("ep.S01E07"))

    assert values["episode_number"] == "7"
    assert values["episode_identifier"] == "S01E07"
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


def test_episode_identifier_and_episode_key_template_values() -> None:
    from backend.utils.output_template import (
        SHOW_OUTPUT_TEMPLATE_FIELDS,
        episode_output_template_values,
        render_output_template,
    )

    cases = (
        ("ep.2497", "2497"),
        ("ep-extra.2497.1", "2497.1"),
        ("ep.S01E07", "S01E07"),
    )

    assert "episode_key" in SHOW_OUTPUT_TEMPLATE_FIELDS
    assert "ep_id" not in SHOW_OUTPUT_TEMPLATE_FIELDS

    for episode_key, expected_identifier in cases:
        values = episode_output_template_values(_episode(episode_key))
        assert values["episode_identifier"] == expected_identifier
        assert values["episode_key"] == episode_key
        assert "ep_id" not in values
        assert render_output_template(
            "/downloads/{{ episode_identifier }} - {{ episode_key }}.ext",
            values,
            allowed_fields=SHOW_OUTPUT_TEMPLATE_FIELDS,
        ) == f"/downloads/{expected_identifier} - {episode_key}.ext"


def test_seasonal_episode_extra_uses_parent_episode_number() -> None:
    from backend.utils.episode import episode_type_info

    assert episode_type_info("ep-extra.S03E12.2") == {
        "type": "ep-extra",
        "number": "12",
    }
