from __future__ import annotations


def test_output_template_expression_spacing_is_canonicalized_on_profile_input() -> None:
    from backend.api.models.local_media_profile import LocalMediaProfileAPICreate

    profile = LocalMediaProfileAPICreate.model_validate({
        "type": "show",
        "name": "Canonical spacing",
        "outputTemplate": "/downloads/{{show_title}}/{{  episode_title  }}.ext",
        "preferredFormat": "format_audio_only",
    })

    assert profile.output_template == "/downloads/{{ show_title }}/{{ episode_title }}.ext"


def test_output_template_spacing_normalizer_preserves_non_print_jinja() -> None:
    from backend.utils.output_template_formatting import normalize_output_template_expression_spacing

    template = (
        "{% set literal = '{{ untouched }}' %}"
        "{# {{ untouched }} #}"
        "{% raw %}{{ untouched }}{% endraw %}"
        "/downloads/{{show_title}}/{{- episode_title -}}.ext"
    )

    assert normalize_output_template_expression_spacing(template) == (
        "{% set literal = '{{ untouched }}' %}"
        "{# {{ untouched }} #}"
        "{% raw %}{{ untouched }}{% endraw %}"
        "/downloads/{{ show_title }}/{{- episode_title -}}.ext"
    )
