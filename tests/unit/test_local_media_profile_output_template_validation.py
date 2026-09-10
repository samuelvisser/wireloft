from __future__ import annotations

import pytest
from pydantic import ValidationError


def _show_profile_payload(output_template: str) -> dict[str, str]:
    return {
        "type": "show",
        "name": "Jinja preamble",
        "outputTemplate": output_template,
        "preferredFormat": "format_audio_only",
    }


def test_output_template_allows_non_outputting_jinja_before_downloads() -> None:
    from backend.api.models.local_media_profile import LocalMediaProfileAPICreate

    output_template = (
        "{% set folder = show_title ~ '-' ~ year %}"
        "/downloads/{{ folder }}/{{ episode_title }}.ext"
    )

    profile = LocalMediaProfileAPICreate.model_validate(
        _show_profile_payload(output_template)
    )

    assert profile.output_template == output_template


def test_output_template_allows_captured_set_block_before_downloads() -> None:
    from backend.api.models.local_media_profile import LocalMediaProfileAPICreate

    output_template = (
        "{% set folder %}{{ show_title }}{% endset %}"
        "/downloads/{{ folder }}/{{ episode_title }}.ext"
    )

    profile = LocalMediaProfileAPICreate.model_validate(
        _show_profile_payload(output_template)
    )

    assert profile.output_template == output_template


def test_output_template_rejects_literal_text_before_downloads() -> None:
    from backend.api.models.local_media_profile import LocalMediaProfileAPICreate

    output_template = (
        "prefix{% set folder = show_title %}"
        "/downloads/{{ folder }}/{{ episode_title }}.ext"
    )

    with pytest.raises(ValidationError, match="must start with '/downloads/'"):
        LocalMediaProfileAPICreate.model_validate(
            _show_profile_payload(output_template)
        )


def test_output_template_rejects_conditional_text_before_downloads() -> None:
    from backend.api.models.local_media_profile import LocalMediaProfileAPICreate

    output_template = (
        "{% if year %}prefix{% endif %}"
        "/downloads/{{ show_title }}/{{ episode_title }}.ext"
    )

    with pytest.raises(ValidationError, match="must start with '/downloads/'"):
        LocalMediaProfileAPICreate.model_validate(
            _show_profile_payload(output_template)
        )


def test_output_template_still_has_to_end_with_ext_on_save() -> None:
    from backend.api.models.local_media_profile import LocalMediaProfileAPICreate

    output_template = (
        "/downloads/{{ show_title }}/{{ episode_title }}.ext"
        "{% set suffix = year %}"
    )

    with pytest.raises(ValidationError, match="must end with '.ext'"):
        LocalMediaProfileAPICreate.model_validate(
            _show_profile_payload(output_template)
        )
