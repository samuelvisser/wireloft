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
        index=42,
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


def test_episode_index_is_the_stored_show_wide_value_not_season_number() -> None:
    from backend.utils.output_template import (
        SHOW_OUTPUT_TEMPLATE_FIELDS, episode_output_template_values, render_output_template,
    )

    for identifier in ("ep.S01E07", "aux.2", "trailer.1"):
        values = episode_output_template_values(_episode(identifier))
        assert values["episode_index"] == "42"
        assert "episode_index" in SHOW_OUTPUT_TEMPLATE_FIELDS
        assert render_output_template(
            "/downloads/{{ episode_index }}-{{ '%03d'|format(episode_index|int) }}.ext",
            values, allowed_fields=SHOW_OUTPUT_TEMPLATE_FIELDS,
        ) == "/downloads/42-042.ext"


def test_episode_index_does_not_require_custom_index_state_or_recount_gaps(monkeypatch) -> None:
    from backend.utils import output_template

    episode = _episode("ep.7")
    episode.index = 105
    monkeypatch.setattr(output_template, "_finish_output_path", lambda rendered, **kwargs: rendered)
    assert output_template.resolve_episode_output_path(
        "/downloads/{{ episode_index }}.ext", episode=episode,
    ) == "/downloads/105.ext"


def test_episode_index_is_not_available_to_movie_profiles() -> None:
    import pytest
    from backend.utils.output_template import MOVIE_OUTPUT_TEMPLATE_FIELDS, validate_output_template_fields

    with pytest.raises(ValueError, match="Unsupported output template variable"):
        validate_output_template_fields(
            "/downloads/{{ episode_index }}.ext", allowed_fields=MOVIE_OUTPUT_TEMPLATE_FIELDS,
        )


def test_episode_index_is_available_in_real_and_fallback_preview_sources() -> None:
    from backend.api.endpoints.local_media_profiles.output_template import (
        _EXAMPLE_SHOW_VALUES, _show_template_source, get_output_template_preview,
    )
    from backend.api.models.local_media_profile import LocalMediaProfileTemplatePreview

    episode = _episode("ep.S01E07")
    episode.id = 987
    source = _show_template_source(episode)
    assert source.values["episode_index"] == "42"
    assert _EXAMPLE_SHOW_VALUES["episode_index"] == "1"
    for values, expected in ((source.values, "42"), (_EXAMPLE_SHOW_VALUES, "1")):
        result = get_output_template_preview(None, LocalMediaProfileTemplatePreview(
            type="show", output_template="/downloads/{{ episode_index }}.ext",
            preferred_format="format_1080p", values=values, indexing_values=[],
        ))
        assert result.output_path == f"/downloads/{expected}.mp4"
        assert result.used_variables == ["episode_index"]
