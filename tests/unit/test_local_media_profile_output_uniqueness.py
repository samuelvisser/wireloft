from __future__ import annotations


def test_canonical_output_resolves_assignments_and_ignores_unused_conditions() -> None:
    from backend.api.endpoints.local_media_profiles.helpers import _canonical_template_patterns

    expected = frozenset({"/downloads/{title}.ext"})

    assert _canonical_template_patterns(
        "/downloads/{{ title }}.ext"
    ) == expected
    assert _canonical_template_patterns(
        "{% set output_title = title %}/downloads/{{ output_title }}.ext"
    ) == expected
    assert _canonical_template_patterns(
        "{% set output_title %}{{ title }}{% endset %}/downloads/{{ output_title }}.ext"
    ) == expected
    assert _canonical_template_patterns(
        "{% if year %}{% set unused = episode %}{% endif %}/downloads/{{ title }}.ext"
    ) == expected
    assert _canonical_template_patterns(
        "/downloads/{% if year %}{{ title }}{% else %}{{ title }}{% endif %}.ext"
    ) == expected


def test_canonical_output_keeps_only_conditionals_that_change_output() -> None:
    from backend.api.endpoints.local_media_profiles.helpers import _canonical_template_patterns

    assert _canonical_template_patterns(
        "/downloads/{% if year %}special/{% endif %}{{ title }}.ext"
    ) == frozenset({
        "/downloads/special/{title}.ext",
        "/downloads/{title}.ext",
    })

    assert _canonical_template_patterns(
        "{% if year %}{% set output_title = title %}"
        "{% else %}{% set output_title = episode %}{% endif %}"
        "/downloads/{{ output_title }}.ext"
    ) == frozenset({
        "/downloads/{title}.ext",
        "/downloads/{episode}.ext",
    })


def test_canonical_output_normalizes_expressions_and_marks_unsupported_jinja() -> None:
    from backend.api.endpoints.local_media_profiles.helpers import _canonical_template_patterns

    assert _canonical_template_patterns(
        "/downloads/{{ title | lower }}.ext"
    ) == _canonical_template_patterns(
        "/downloads/{{title|lower}}.ext"
    )
    assert _canonical_template_patterns(
        "/downloads/{% for value in title %}{{ value }}{% endfor %}.ext"
    ) is None
