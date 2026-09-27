from __future__ import annotations

import re

from jinja2.sandbox import ImmutableSandboxedEnvironment
import pytest

from backend.utils.show_media_directory import infer_show_media_directory


def _root(template, **kwargs):
    values = dict(show='my-show', show_title='My Show', meta_show_folder='Custom Show',
                  season_name='Introduction', season_number='1', year='2026', date='2026-09-27',
                  episode_type='ep', title='First', episode='first', episode_title='First')
    environment = ImmutableSandboxedEnvironment()
    environment.globals.clear()
    environment.finalize = lambda value: ''.join(c for c in str(value or '').replace('/', '_').replace('\\', '_') if ord(c) >= 32)
    environment.filters['custom_index'] = lambda _key: pytest.fail('Must not calculate an index')
    return infer_show_media_directory(template, values, environment=environment,
                                     sanitize_component=lambda value: re.sub(r'[<>:"\\|?*]', '_', value), **kwargs)


@pytest.mark.parametrize(('template', 'expected'), [
    ('/downloads/TV/{{ show_title }}/Season {{ season_number }}/{{ title }}.ext', '/downloads/TV/My Show'),
    ('/downloads/Podcasts/{{ show_title }}/{{ date }} - {{ title }}.ext', '/downloads/Podcasts/My Show'),
    ('/downloads/{{ show }}/{{ year }}/{{ title }}.ext', '/downloads/my-show'),
    ('/downloads/{{ show }}/{{ season_name }}/{{ title }}.ext', '/downloads/my-show'),
    ('/downloads/{{ show }}/Season 01/{{ title }}.ext', '/downloads/my-show'),
    ('/downloads/{{ show }}/S.01/{{ title }}.ext', '/downloads/my-show'),
    ('/downloads/{{ show }}/Extras/{{ title }}.ext', '/downloads/my-show'),
    ('/downloads/{{ show }}/audio/{{ title }}.ext', '/downloads/my-show/audio'),
    ('/downloads/TV/My Show/Season 01/{{ title }}.ext', '/downloads/TV/My Show'),
    ('/downloads/{{ meta_show_folder }}/{{ title }}.ext', '/downloads/Custom Show'),
    ('{% set name = show_title|lower %}/downloads/{{ name }}/{{ title }}.ext', '/downloads/my show'),
    ('{% set name %}{{ show_title|upper }}{% endset %}/downloads/{{ name }}/{{ title }}.ext', '/downloads/MY SHOW'),
    ('{% macro folder(value) %}{{ value|upper }}{% endmacro %}/downloads/{{ folder(show) }}/{{ title }}.ext', '/downloads/MY-SHOW'),
    ('{% with name = show_title %}/downloads/{{ name }}/{{ title }}.ext{% endwith %}', '/downloads/My Show'),
    ('/downloads/{{ show }}/{% if year %}{{ year }}/{% endif %}{{ title }}.ext', '/downloads/my-show'),
    ("/downloads/{{ show }}/{% if episode_type == 'aux' %}Extras/{% else %}Episodes/{% endif %}{{ title }}.ext", '/downloads/my-show'),
    ("{% if episode_type == 'aux' %}{% set section='Extras' %}{% else %}{% set section='Episodes' %}{% endif %}/downloads/{{ show }}/{{ section }}/{{ title }}.ext", '/downloads/my-show'),
    ("{% set section = 'order'|custom_index %}/downloads/{{ show }}/{{ section }}/{{ title }}.ext", '/downloads/my-show'),
    ("/downloads/{{ show }}/{{ 'order'|custom_index }}/{{ title }}.ext", '/downloads/my-show'),
    ("{% if episode_type == 'aux' %}/downloads/Extras/{{ show }}/{% else %}/downloads/Shows/{{ show }}/{% endif %}{{ title }}.ext", None),
    ('/downloads/{{ year }}/{{ show }}/{{ title }}.ext', None),
    ('/downloads/TV/{{ title }}.ext', None),
    ('/downloads/{{ show_title|random }}/{{ title }}.ext', None),
    ('/downloads/../{{ show }}/{{ title }}.ext', None),
    ('/outside/{{ show }}/{{ title }}.ext', None),
    ("{% include 'external' %}", None),
    ('/downloads/{{ show }}/{{ 1 / 0 }}/{{ title }}.ext', None),
])
def test_show_directory_policy_on_shared_analysis(template, expected):
    result = _root(template)
    assert result.path == expected
    assert bool(result.reason) is (expected is None)


def test_known_literal_season_names():
    assert _root('/downloads/{{ show }}/Introduction/{{ title }}.ext', season_names=('Introduction',)).path == '/downloads/my-show'


def test_filename_only_complexity_does_not_limit_a_clear_show_root():
    helpers = '{% if year %}{% set label=title %}{% else %}{% set label=episode %}{% endif %}' * 12
    assert _root(helpers + '/downloads/{{ show }}/{{ label }}.ext').path == '/downloads/my-show'
    assert _root('/downloads/{{ show }}/' + '{% if year %}a{% else %}b{% endif %}' * 12 + '{{ title }}.ext').path == '/downloads/my-show'


def test_correlated_directory_branches_do_not_invent_impossible_layouts():
    template = '/downloads/{{ show }}/{% if year %}A/{% else %}B/{% endif %}{% if not year %}X/{% endif %}{{title}}.ext'
    assert _root(template).path == '/downloads/my-show'
