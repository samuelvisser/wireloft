import pytest


def _render(template: str, title: str) -> str:
    from backend.utils.output_template import SHOW_OUTPUT_TEMPLATE_FIELDS, render_output_template

    return render_output_template(
        template,
        {"title": title},
        allowed_fields=SHOW_OUTPUT_TEMPLATE_FIELDS,
    )


def test_strftime_formats_wireloft_date_and_datetime_values() -> None:
    from backend.utils.output_template import SHOW_OUTPUT_TEMPLATE_FIELDS, render_output_template

    assert render_output_template(
        '/downloads/{{ date | strftime("%d-%m-%Y") }}.ext',
        {"date": "2026-09-24"},
        allowed_fields=SHOW_OUTPUT_TEMPLATE_FIELDS,
    ) == "/downloads/24-09-2026.ext"

    assert render_output_template(
        '/downloads/{{ datetime | strftime("%Y%m%d-%H%M%S") }}.ext',
        {"datetime": "2026-09-24 20:13:05"},
        allowed_fields=SHOW_OUTPUT_TEMPLATE_FIELDS,
    ) == "/downloads/20260924-201305.ext"


def test_strftime_keeps_missing_date_empty() -> None:
    from backend.utils.output_template import SHOW_OUTPUT_TEMPLATE_FIELDS, render_output_template

    assert render_output_template(
        '/downloads/prefix{{ date | strftime("%Y%m%d") }}.ext',
        {"date": ""},
        allowed_fields=SHOW_OUTPUT_TEMPLATE_FIELDS,
    ) == "/downloads/prefix.ext"


def test_strftime_rejects_non_date_values() -> None:
    from backend.utils.output_template import SHOW_OUTPUT_TEMPLATE_FIELDS, render_output_template

    with pytest.raises(ValueError, match="strftime requires a WireLoft date/time value"):
        render_output_template(
            '/downloads/{{ date | strftime("%Y%m%d") }}.ext',
            {"date": "not-a-date"},
            allowed_fields=SHOW_OUTPUT_TEMPLATE_FIELDS,
        )


def test_regex_replace_replaces_all_matches_by_default() -> None:
    rendered = _render(
        "/downloads/{{ title | regex_replace('(?<=[0-9])[xX](?=[0-9])', '-by-') }}.ext",
        "6x6 and 10X10",
    )

    assert rendered == "/downloads/6-by-6 and 10-by-10.ext"


def test_regex_replace_accepts_optional_count() -> None:
    rendered = _render(
        "/downloads/{{ title | regex_replace('(?<=[0-9])[xX](?=[0-9])', '-by-', count=1) }}.ext",
        "6x6 and 10x10",
    )

    assert rendered == "/downloads/6-by-6 and 10x10.ext"


def test_regex_search_returns_boolean_for_jinja_conditionals() -> None:
    template = (
        "/downloads/{% if title | regex_search('(?<=[0-9])[xX](?=[0-9])') %}"
        "matched{% else %}unmatched{% endif %}.ext"
    )

    assert _render(template, "Episode 6x6") == "/downloads/matched.ext"
    assert _render(template, "Episode Six") == "/downloads/unmatched.ext"


def test_invalid_regex_is_reported_as_template_error() -> None:
    with pytest.raises(ValueError, match="Invalid regular expression"):
        _render(
            "/downloads/{{ title | regex_replace('(', '-by-') }}.ext",
            "6x6",
        )


def test_invalid_regex_replacement_is_reported_as_template_error() -> None:
    with pytest.raises(ValueError, match="Invalid regular expression replacement"):
        _render(
            "/downloads/{{ title | regex_replace('(x)', '\\2') }}.ext",
            "6x6",
        )


def test_preview_returns_invalid_regex_as_field_validation_error() -> None:
    from fastapi import HTTPException

    from backend.api.endpoints.local_media_profiles.router import local_media_profile_template_preview
    from backend.api.models.local_media_profile import LocalMediaProfileTemplatePreview

    body = LocalMediaProfileTemplatePreview(
        type="show",
        preferred_format="format_audio_only",
        output_template="/downloads/{{ title | regex_search('(') }}.ext",
        values={"title": "Example"},
    )

    with pytest.raises(HTTPException) as exc_info:
        local_media_profile_template_preview(body)

    assert exc_info.value.status_code == 422
    assert "Invalid regular expression" in exc_info.value.detail[0]["msg"]


def test_regex_filters_are_isolated_to_output_template_environment() -> None:
    from jinja2 import Environment

    from backend.utils.output_template_jinja import create_output_template_environment

    output_template_environment = create_output_template_environment()

    assert "regex_replace" in output_template_environment.filters
    assert "regex_search" in output_template_environment.filters
    assert "strftime" in output_template_environment.filters
    assert "regex_replace" not in Environment().filters
    assert "regex_search" not in Environment().filters
    assert "strftime" not in Environment().filters
