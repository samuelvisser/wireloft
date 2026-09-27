from __future__ import annotations

import re

from jinja2.sandbox import SandboxedEnvironment
import pytest

from backend.utils.show_media_directory import infer_show_media_directory


def _resolve(template, *, values=None, seasons=(), sanitizer=lambda value: value):
    context = {
        "show": "my-show", "show_title": "My Show", "season_number": "1",
        "season_name": "Introduction", "season_index": "1", "season_type": "normal",
        "episode": "first", "episode_title": "First", "title": "First",
        "episode_type": "ep", "year": "2026", "date": "2026-09-27",
        "meta_show_folder": "Custom Show",
    }
    context.update(values or {})
    environment = SandboxedEnvironment()
    environment.finalize = lambda value: "".join(
        character for character in str(value if value is not None else "").replace("/", "_").replace("\\", "_")
        if ord(character) >= 32
    )

    def no_index_assignment(_key):
        raise AssertionError("Root inference must not allocate or simulate an episode index")

    environment.filters["custom_index"] = no_index_assignment
    return infer_show_media_directory(
        template, context, environment=environment,
        sanitize_component=sanitizer, season_names=seasons,
    )


@pytest.mark.parametrize(("template", "expected"), [
    ("/downloads/TV/{{ show_title }}/Season {{ season_number }}/{{ title }}.ext", "/downloads/TV/My Show"),
    ("/downloads/Podcasts/{{ show_title }}/{{ date }} - {{ title }}.ext", "/downloads/Podcasts/My Show"),
    ("/downloads/{{ show }}/{{ year }}/{{ title }}.ext", "/downloads/my-show"),
    ("/downloads/{{ show }}/{{ season_name }}/{{ title }}.ext", "/downloads/my-show"),
    ("/downloads/{{ show }}/Season 01/{{ title }}.ext", "/downloads/my-show"),
    ("/downloads/{{ show }}/S.01/{{ title }}.ext", "/downloads/my-show"),
    ("/downloads/{{ show }}/Extras/{{ title }}.ext", "/downloads/my-show"),
    ("/downloads/{{ show }}/audio/{{ title }}.ext", "/downloads/my-show/audio"),
    ("/downloads/TV/My Show/Season 01/{{ title }}.ext", "/downloads/TV/My Show"),
    ("/downloads/{{ meta_show_folder }}/{{ title }}.ext", "/downloads/Custom Show"),
    ("{% set name = show_title|lower %}/downloads/{{ name }}/{{ title }}.ext", "/downloads/my show"),
    ("{% set name %}{{ show_title|upper }}{% endset %}/downloads/{{ name }}/{{ title }}.ext", "/downloads/MY SHOW"),
    ("{% macro folder(value) %}{{ value|upper }}{% endmacro %}/downloads/{{ folder(show) }}/{{ title }}.ext", "/downloads/MY-SHOW"),
    ("{% with name = show_title %}/downloads/{{ name }}/{{ title }}.ext{% endwith %}", "/downloads/My Show"),
    ("/downloads/{{ show }}/{% if year %}{{ year }}/{% endif %}{{ title }}.ext", "/downloads/my-show"),
    ("/downloads/{{ show }}/{% if episode_type == 'aux' %}Extras/{% else %}Episodes/{% endif %}{{ title }}.ext", "/downloads/my-show"),
    ("{% if episode_type == 'aux' %}{% set section = 'Extras' %}{% else %}{% set section = 'Episodes' %}{% endif %}/downloads/{{ show }}/{{ section }}/{{ title }}.ext", "/downloads/my-show"),
    ("{% set section = 'order'|custom_index %}/downloads/{{ show }}/{{ section }}/{{ title }}.ext", "/downloads/my-show"),
    ("/downloads/{{ show }}/{{ 'order'|custom_index }}/{{ title }}.ext", "/downloads/my-show"),
    ("/downloads/{% if meta_show_folder %}{{ meta_show_folder }}{% else %}{{ show }}{% endif %}/{{ title }}.ext", "/downloads/Custom Show"),
    ("{% if episode_type == 'aux' %}/downloads/Extras/{{ show }}/{% else %}/downloads/Shows/{{ show }}/{% endif %}{{ title }}.ext", None),
    ("/downloads/{{ year }}/{{ show }}/{{ title }}.ext", None),
    ("/downloads/TV/{{ title }}.ext", None),
    ("/downloads/{{ title }}.ext", None),
    ("/downloads/{{ show_title|random }}/{{ title }}.ext", None),
    ("/downloads/../{{ show }}/{{ title }}.ext", None),
    ("/outside/{{ show }}/{{ title }}.ext", None),
    ("{% include 'external.jinja' %}", None),
])
def test_semantic_show_roots(template, expected):
    result = _resolve(template)
    assert result.path == expected
    assert bool(result.reason) is (expected is None)


def test_single_episode_does_not_make_a_season_or_date_the_show_root():
    template = "/downloads/{{ show }}/{{ season_number }}/{{ year }}/{{ title }}.ext"
    first = _resolve(template, values={"season_number": "1", "year": "2026"})
    future = _resolve(template, values={"season_number": "7", "year": "2032"})
    assert first.path == future.path == "/downloads/my-show"


def test_known_literal_season_name_is_not_a_show_directory():
    assert _resolve("/downloads/{{ show }}/Introduction/{{ title }}.ext", seasons=("Introduction",)).path == "/downloads/my-show"


def test_full_path_components_are_sanitized_after_jinja_filters():
    result = _resolve(
        "/downloads/{{ show_title|replace(':', '-') }}/{{ title }}.ext",
        values={"show_title": "Host: My Show?"},
        sanitizer=lambda value: re.sub(r'[<>:"/\\|?*]', "_", value),
    )
    assert result.path == "/downloads/Host- My Show_"


def test_show_metadata_cannot_inject_path_structure_or_annotations():
    result = _resolve("/downloads/{{ show_title }}/{{ title }}.ext", values={"show_title": "My/Show\x01"})
    assert result.path == "/downloads/My_Show"


def test_custom_metadata_fallback_uses_real_show_values():
    result = _resolve(
        "/downloads/{% if meta_show_folder %}{{ meta_show_folder }}{% else %}{{ show }}{% endif %}/{{ title }}.ext",
        values={"meta_show_folder": ""},
    )
    assert result.path == "/downloads/my-show"


def test_many_variable_directories_keep_only_the_proven_show_prefix():
    template = "/downloads/{{ show }}/" + "{% if year %}a{% else %}b{% endif %}/" * 7 + "{{ title }}.ext"
    result = _resolve(template)
    assert result.path == "/downloads/my-show"


def test_invalid_show_expression_reports_reason_without_traceback():
    result = _resolve("/downloads/{{ show }}/{{ 1 / 0 }}/{{ title }}.ext")
    assert result.path is None
    assert result.reason


def test_complex_filename_conditions_do_not_limit_a_clear_show_root():
    filename = "{% if year %}a{% else %}b{% endif %}" * 12 + "{{ title }}.ext"
    assert _resolve("/downloads/{{ show }}/" + filename).path == "/downloads/my-show"


def test_filename_only_assignment_branches_are_not_evaluated():
    helpers = "{% if year %}{% set label = title %}{% else %}{% set label = episode %}{% endif %}" * 12
    assert _resolve(helpers + "/downloads/{{ show }}/{{ label }}.ext").path == "/downloads/my-show"


def test_repeated_show_name_can_still_be_a_known_literal_season():
    assert _resolve("/downloads/{{ show_title }}/My Show/{{ title }}.ext", seasons=("My Show",)).path == "/downloads/My Show"


def test_filename_trimming_does_not_confuse_equal_output_nodes():
    template = "/downloads/{{ show }}/a/{% if year %}b{% else %}c{% endif %}/fixed/{{ title }}.ext"
    assert _resolve(template).path == "/downloads/my-show/a"
