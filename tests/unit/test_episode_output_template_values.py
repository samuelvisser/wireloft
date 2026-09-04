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
    assert values["episode_label"] == "S01E07"
    assert values["episode_identifier"] == "ep.S01E07"
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


def test_episode_label_and_episode_identifier_template_values() -> None:
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

    assert "episode_label" in SHOW_OUTPUT_TEMPLATE_FIELDS
    assert "episode_identifier" in SHOW_OUTPUT_TEMPLATE_FIELDS
    assert "episode_key" not in SHOW_OUTPUT_TEMPLATE_FIELDS
    assert "ep_id" not in SHOW_OUTPUT_TEMPLATE_FIELDS

    for episode_identifier, expected_label in cases:
        values = episode_output_template_values(_episode(episode_identifier))
        assert values["episode_label"] == expected_label
        assert values["episode_identifier"] == episode_identifier
        assert "episode_key" not in values
        assert "ep_id" not in values
        assert render_output_template(
            "/downloads/{{ episode_label }} - {{ episode_identifier }}.ext",
            values,
            allowed_fields=SHOW_OUTPUT_TEMPLATE_FIELDS,
        ) == f"/downloads/{expected_label} - {episode_identifier}.ext"


def test_seasonal_episode_extra_uses_parent_episode_number() -> None:
    from backend.utils.episode import episode_type_info

    assert episode_type_info("ep-extra.S03E12.2") == {
        "type": "ep-extra",
        "number": "12",
    }
