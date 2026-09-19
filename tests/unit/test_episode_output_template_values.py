from types import SimpleNamespace


def _episode(identifier: str, *, dw_episode_number: str | None = None):
    return SimpleNamespace(
        show=SimpleNamespace(slug="chip-chilla", title="Chip Chilla", custom_metadata=None),
        season=SimpleNamespace(
            slug="season-1",
            name="Season 1",
            index=4,
            season_type="normal",
            season_number=1,
        ),
        slug="chips-odyssey",
        title="Chip's Odyssey",
        episode_identifier=identifier,
        dw_episode_number=dw_episode_number,
        published_date=None,
    )


def test_seasonal_episode_number_renders_as_numeric_episode_number() -> None:
    from backend.utils.output_template import (
        SHOW_OUTPUT_TEMPLATE_FIELDS,
        episode_output_template_values,
        render_output_template,
    )

    values = episode_output_template_values(_episode("ep.S01E07", dw_episode_number="7.00"))

    assert values["season_index"] == "4"
    assert values["season_number"] == "1"
    assert values["season_type"] == "normal"
    assert values["dw_episode_number"] == "7.00"
    assert values["episode_number"] == "7"
    assert values["episode_label"] == "S01E07"
    assert values["episode_identifier"] == "ep.S01E07"
    assert render_output_template(
        "/downloads/Video/{{ show_title }}/Season {{ \"%02d\"|format(season_number|int) }}/"
        "{{ show_title }} - S{{ \"%02d\"|format(season_number|int) }}"
        "E{{ \"%02d\"|format(episode_number|int) }} - {{ title }}.ext",
        values,
        allowed_fields=SHOW_OUTPUT_TEMPLATE_FIELDS,
    ) == (
        "/downloads/Video/Chip Chilla/Season 01/"
        "Chip Chilla - S01E07 - Chip's Odyssey.ext"
    )


def test_episode_identifier_semantics_are_exposed_to_templates() -> None:
    from backend.utils.output_template import (
        SHOW_OUTPUT_TEMPLATE_FIELDS,
        episode_output_template_values,
        render_output_template,
    )

    values = episode_output_template_values(
        _episode(
            "ep-extra.trailer.S03E12.5",
            dw_episode_number="12.05",
        )
    )

    assert values["episode_type"] == "ep-extra"
    assert values["episode_extra_type"] == "trailer"
    assert values["episode_number"] == "12"
    assert values["episode_sub_number"] == "5"
    assert values["episode_label"] == "S03E12.5"
    assert values["dw_episode_number"] == "12.05"
    assert {
        "season_type",
        "season_number",
        "dw_episode_number",
        "episode_extra_type",
        "episode_sub_number",
    }.issubset(SHOW_OUTPUT_TEMPLATE_FIELDS)

    assert render_output_template(
        "/downloads/{{ episode_label }}-{{ episode_extra_type }}{{ episode_sub_number }}.ext",
        values,
        allowed_fields=SHOW_OUTPUT_TEMPLATE_FIELDS,
    ) == "/downloads/S03E12.5-trailer5.ext"


def test_episode_identifier_info_extracts_parent_and_sub_episode_numbers() -> None:
    from backend.utils.episode import EpisodeIdentifierInfo

    info = EpisodeIdentifierInfo.from_identifier("ep-extra.other.S03E12.2")

    assert info.type == "ep-extra"
    assert info.extra_type == "other"
    assert info.season_number == 3
    assert info.episode_number == "12"
    assert info.sub_episode_number == "2"
