from __future__ import annotations

import re

from jinja2 import StrictUndefined
from jinja2.sandbox import ImmutableSandboxedEnvironment
import pytest

from backend.utils.jinja_analysis.comparison import OutputOverlap
from backend.utils.output_template_analysis import analyze_profile_outputs, compare_profile_outputs


def _environment():
    environment = ImmutableSandboxedEnvironment(autoescape=False, undefined=StrictUndefined)
    environment.globals.clear()
    environment.finalize = lambda value: str(value if value is not None else '').replace('/', '_').replace('\\', '_')
    return environment


def _compare(left, right, *, kind='show', left_format='format_1080p', right_format='format_1080p', finalize=None):
    environment = _environment()
    lhs = analyze_profile_outputs(left, kind, left_format, environment=environment, namespace='left')
    rhs = analyze_profile_outputs(right, kind, right_format, environment=environment, namespace='right')
    return compare_profile_outputs(lhs, rhs, environment=environment,
                                   finalize_path=finalize or (lambda path, ext: path[:-3] + ext)).status


@pytest.mark.parametrize('template', [
    '/downloads/{{ title }}.ext',
    '{% set output_title = title %}/downloads/{{ output_title }}.ext',
    '{% set output_title %}{{ title }}{% endset %}/downloads/{{ output_title }}.ext',
    '{% if year %}{% set unused = episode %}{% endif %}/downloads/{{ title }}.ext',
    '/downloads/{% if year %}{{ title }}{% else %}{{ title }}{% endif %}.ext',
])
def test_assignment_normalization_and_unused_conditions(template):
    assert _compare(template, '/downloads/{{ title }}.ext') == OutputOverlap.OVERLAP


def test_output_affecting_conditionals_are_preserved():
    template = '/downloads/{% if year %}special/{% endif %}{{ title }}.ext'
    assert _compare(template, '/downloads/special/{{ title }}.ext') == OutputOverlap.OVERLAP
    assert _compare(template, '/downloads/{{ title }}.ext') == OutputOverlap.OVERLAP
    assert _compare(template, '/downloads/other/{{ title }}.ext') != OutputOverlap.OVERLAP
    choice = '{% if year %}{% set output_title = title %}{% else %}{% set output_title = episode %}{% endif %}/downloads/{{ output_title }}.ext'
    assert _compare(choice, '/downloads/{{ title }}.ext') == OutputOverlap.OVERLAP
    assert _compare(choice, '/downloads/{{ episode }}.ext') == OutputOverlap.OVERLAP


def test_expression_spacing_is_not_semantic():
    assert _compare('/downloads/{{ title | lower }}.ext', '/downloads/{{title|lower}}.ext') == OutputOverlap.OVERLAP


def test_unknown_is_distinct_from_disjoint():
    assert _compare('/downloads/{% for value in title %}{{ value }}{% endfor %}.ext',
                    '/downloads/{{ title }}.ext') == OutputOverlap.UNKNOWN


@pytest.mark.parametrize(('left', 'right'), [
    ('title', 'episode_title'), ('date', 'episode_published_date'),
    ('time', 'episode_published_time'), ('datetime', 'episode_published_datetime'),
])
def test_guaranteed_episode_aliases(left, right):
    assert _compare('/downloads/{{ '+left+' }}.ext', '/downloads/{{ '+right+' }}.ext') == OutputOverlap.OVERLAP


@pytest.mark.parametrize(('left', 'right'), [
    ('slug', 'movie_slug'), ('title', 'movie_title'), ('extended_title', 'movie_extended_title'),
    ('year', 'movie_year'), ('author', 'movie_author'), ('rating', 'movie_mature_rating'),
])
def test_movie_feature_aliases(left, right):
    assert _compare('/downloads/{{ '+left+' }}.ext', '/downloads/{{ '+right+' }}.ext', kind='movie') == OutputOverlap.OVERLAP


def test_movie_extras_are_not_mapped_to_parent_movie_title():
    left = '/downloads/{% if media_type == "movie" %}A/{% else %}extras/{% endif %}{{ title }}.ext'
    right = '/downloads/{% if media_type == "movie" %}B/{% else %}extras/{% endif %}{{ movie_title }}.ext'
    assert _compare(left, right, kind='movie') == OutputOverlap.UNKNOWN


def test_an_extra_only_collision_is_detected():
    left = '/downloads/{% if media_type == "movie" %}A/{% else %}extras/{% endif %}{{ title }}.ext'
    right = '/downloads/{% if media_type == "movie" %}B/{% else %}extras/{% endif %}{{ extended_title }}.ext'
    assert _compare(left, right, kind='movie') == OutputOverlap.OVERLAP


@pytest.mark.parametrize(('left_format', 'right_format', 'expected'), [
    ('format_4k', 'format_720p', OutputOverlap.OVERLAP),
    ('format_1080p', 'format_720p', OutputOverlap.OVERLAP),
    ('format_1080p', 'format_audio_only', OutputOverlap.DISJOINT),
    ('format_1080p', 'format_hls', OutputOverlap.DISJOINT),
])
def test_format_families(left_format, right_format, expected):
    assert _compare('/downloads/{{ title }}.ext', '/downloads/{{ title }}.ext',
                    left_format=left_format, right_format=right_format) == expected


def test_filename_restrictions_are_considered():
    def windows(path, ext):
        return '/'.join(re.sub(r'[<>:"\\|?*]', '_', part).rstrip(' .') for part in (path[:-3] + ext).split('/'))
    assert _compare('/downloads/A:B/{{ title }}.ext', '/downloads/A?B/{{ title }}.ext', finalize=windows) == OutputOverlap.OVERLAP


def test_profile_scoped_indexes_do_not_create_false_guard_contradictions():
    environment = _environment()
    environment.filters['custom_index'] = lambda _key: pytest.fail('Must remain symbolic')
    lhs = analyze_profile_outputs("{% if 'x'|custom_index == 1 %}/downloads/same.ext{% else %}/downloads/left.ext{% endif %}",
                                  'show', 'format_1080p', environment=environment, namespace='left')
    rhs = analyze_profile_outputs("{% if 'x'|custom_index != 1 %}/downloads/same.ext{% else %}/downloads/right.ext{% endif %}",
                                  'show', 'format_1080p', environment=environment, namespace='right')
    assert compare_profile_outputs(lhs, rhs, environment=environment,
                                   finalize_path=lambda path, ext: path[:-3]+ext).status == OutputOverlap.OVERLAP


def test_source_and_profile_types_are_separate():
    environment = _environment()
    left = analyze_profile_outputs('/downloads/{{ title }}.ext', 'show', 'format_1080p', environment=environment, namespace='left')
    right = analyze_profile_outputs('/downloads/{{ title }}.ext', 'movie', 'format_1080p', environment=environment, namespace='right')
    assert compare_profile_outputs(left, right, environment=environment,
                                   finalize_path=lambda path, ext: path[:-3]+ext).status == OutputOverlap.DISJOINT


def test_create_and_update_use_conditional_collision_analysis():
    pytest.importorskip('backend.db')
    from fastapi import HTTPException
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from backend.db import Base
    import backend.db.models  # noqa: F401
    from backend.api.endpoints.show_local_media_profiles.service import create_show_local_media_profile, update_show_local_media_profile
    from backend.api.models.show_local_media_profile import ShowLocalMediaProfileAPICreate, ShowLocalMediaProfileAPIUpdate

    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            original = create_show_local_media_profile(session, ShowLocalMediaProfileAPICreate(
                name='Original', preferred_format='format_1080p',
                output_template='/downloads/{% if episode_type == "aux" %}Extras/{% else %}Episodes/{% endif %}{{ episode_title }}.ext'))
            with pytest.raises(HTTPException) as conflict:
                create_show_local_media_profile(session, ShowLocalMediaProfileAPICreate(
                    name='Conflicting', preferred_format='format_720p',
                    output_template='{% macro label(value) %}{{ value }}{% endmacro %}/downloads/Extras/{{ label(title) }}.ext'))
            assert conflict.value.status_code == 409
            assert conflict.value.detail[0]['loc'] == ['body', 'outputTemplate']
            assert conflict.value.detail[0]['type'] == 'output_path_collision'
            assert 'Original' in conflict.value.detail[0]['msg']
            separate = create_show_local_media_profile(session, ShowLocalMediaProfileAPICreate(
                name='Separate', preferred_format='format_1080p', output_template='/downloads/Separate/{{ title }}.ext'))
            with pytest.raises(HTTPException):
                update_show_local_media_profile(session, separate.slug, ShowLocalMediaProfileAPIUpdate(
                    name='Separate', preferred_format='format_1080p', output_template='/downloads/Extras/{{ title }}.ext'))
            update_show_local_media_profile(session, original.slug, ShowLocalMediaProfileAPIUpdate(
                name='Original', preferred_format='format_1080p', output_template=original.output_template))
    finally:
        engine.dispose()


def test_mutually_exclusive_layouts_are_not_rejected_by_the_api():
    pytest.importorskip('backend.db')
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from backend.db import Base
    import backend.db.models  # noqa: F401
    from backend.api.endpoints.show_local_media_profiles.service import create_show_local_media_profile
    from backend.api.models.show_local_media_profile import ShowLocalMediaProfileAPICreate
    engine = create_engine('sqlite:///:memory:')
    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            for name, condition in [('A', '=='), ('B', '!=')]:
                create_show_local_media_profile(session, ShowLocalMediaProfileAPICreate(
                    name=name, preferred_format='format_1080p',
                    output_template='/downloads/{% if episode_type '+condition+' "aux" %}Shared/{% else %}'+name+'/{% endif %}{{ title }}.ext'))
    finally:
        engine.dispose()
