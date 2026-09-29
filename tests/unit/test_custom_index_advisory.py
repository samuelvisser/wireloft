from collections import defaultdict
from itertools import product

import pytest
from jinja2 import StrictUndefined, pass_context
from jinja2.sandbox import ImmutableSandboxedEnvironment

from backend.utils.jinja_analysis.custom_index_advisory import get_custom_index_advisories


@pytest.fixture
def environment():
    env = ImmutableSandboxedEnvironment(undefined=StrictUndefined, autoescape=False, keep_trailing_newline=True)
    env.globals.clear()
    env.finalize = lambda value: str(value if value is not None else '').replace('/', '_').replace('\\', '_')

    @pass_context
    def custom_index(context, key):
        return context['resolve'](key)

    env.filters['custom_index'] = custom_index
    env.filters['regex_replace'] = lambda value, pattern, replacement: value
    return env


def advisory(environment, template, definitions=('extra',)):
    return get_custom_index_advisories(template, definition_keys=definitions, environment=environment)


PLEX = (
    '{# Variables #}'
    '{% set season_num = "%02d"|format(season_number|int) %}'
    '{% set ep_num = "%02d"|format(episode_number|int) %}'
    "{% set is_extra = season_type == 'extra' or episode_type == 'aux' or episode_type == 'trailer' %}"
    "{% set extra_num = 'extra' | custom_index %}"
    "{% set plex_year = ' (' ~ meta_show_year ~ ')' if meta_show_year %}"
    "{% set plex_show_title = show_title ~ plex_year %}"
    "{% set plex_season = 'Specials' if is_extra else 'Season ' ~ season_num %}"
    "{% set plex_ep_id = 'other' ~ extra_num if is_extra else 'S' ~ season_num ~ 'E' ~ ep_num %}"
    "{% set plex_title = title | replace('[', '(') | replace(']', ')') %}"
    '{# Path #}/downloads/Video/The Daily Wire Shows/{{ plex_show_title }}/{{ plex_season }}/'
    '{{ plex_show_title }} - {{ plex_ep_id }} [{{ plex_title }}].ext'
)


def test_reversed_inline_condition_still_gets_a_safe_set_block_suggestion(environment):
    source = (
        "{% set season_num = '%02d'|format(season_index|int) %}"
        "{% set ep_num = '%02d'|format(episode_number|int) %}"
        "{% set plex_year = ' (' ~ meta_show_year ~ ')' if meta_show_year != '' else '' %}"
        "{% set extra_num='extra'|custom_index %}"
        "{% set is_extra = season_type == 'extra' or episode_type == 'aux' or episode_type == 'trailer' %}"
        "{% set plex_season = 'Season ' ~ season_num if not is_extra else 'Specials' %}"
        "{% set plex_ep_id = 'S' ~ season_num ~ 'E' ~ ep_num if not is_extra else 'extra' ~ extra_num %}"
        "/downloads/{{ plex_season }}/{{ plex_ep_id }}{{ plex_year }}.ext"
    )
    item, = advisory(environment, source).advisories
    suggestion = item.suggestion
    assert suggestion is not None
    assert "'extra' | custom_index" in suggestion.after
    assert "if not (is_extra)" in suggestion.after
    assert "{% set extra_num=" not in suggestion.output_template

    for is_extra in (False, True):
        used = []
        values = dict(
            season_index='1',
            episode_number='4',
            meta_show_year='',
            season_type='extra' if is_extra else 'normal',
            episode_type='ep',
            resolve=lambda key: used.append(key) or 7,
        )
        before = environment.from_string(source).render(values)
        used.clear()
        after = environment.from_string(suggestion.output_template).render(values)
        assert after == before
        assert bool(used) == is_extra


def test_no_else_inline_condition_gets_a_safe_conditional_set_block(environment):
    source = (
        '{# Variables #}'
        '{% set season_num = "%02d"|format(season_number|int) %}'
        '{% set ep_num = "%02d"|format(episode_number|int) %}'
        "{% set is_extra = season_type == 'extra' or episode_type == 'aux' or episode_type == 'trailer' %}"
        "{% set extra_num = 'extra' | custom_index %}"
        "{% set plex_year = ' (' ~ meta_show_year ~ ')' if meta_show_year %}"
        "{% set plex_show_title = show_title ~ plex_year %}"
        "{% set plex_season = 'Specials' if is_extra else 'Season ' ~ season_num %}"
        "{% set plex_ep_id = 'other' ~ extra_num if is_extra %}"
        "/downloads/{{ plex_show_title }}/{{ plex_season }}/{{ plex_ep_id }}.ext"
    )
    item, = advisory(environment, source).advisories
    suggestion = item.suggestion
    assert suggestion is not None
    assert "{% set extra_num =" not in suggestion.output_template
    assert suggestion.after == (
        "{% set plex_ep_id %}{% if is_extra %}"
        "other{{ 'extra' | custom_index }}{% endif %}{% endset %}"
    )
    assert not advisory(environment, suggestion.output_template).advisories

    for episode_type, expected_use in (('ep', False), ('aux', True)):
        before_used = []
        after_used = []
        values = dict(
            season_number='1',
            episode_number='4',
            season_type='normal',
            episode_type=episode_type,
            meta_show_year='',
            show_title='A Show',
        )
        before = environment.from_string(source).render(
            **values, resolve=lambda key: before_used.append(key) or 7,
        )
        after = environment.from_string(suggestion.output_template).render(
            **values, resolve=lambda key: after_used.append(key) or 7,
        )
        assert after == before
        assert before_used == ['extra']
        assert bool(after_used) == expected_use


def test_no_else_inline_condition_preserves_undefined_with_an_expression_rewrite(environment):
    source = (
        "{% set n='extra'|custom_index %}"
        "{% set label='extra' ~ n if flag %}"
        "/downloads/{{ label | default('missing') }}.ext"
    )
    item, = advisory(environment, source).advisories
    assert item.suggestion is not None
    assert "{% set label %}" not in item.suggestion.output_template
    for flag in (False, True):
        values = dict(flag=flag, resolve=lambda key: 7)
        assert environment.from_string(item.suggestion.output_template).render(values) == environment.from_string(source).render(values)


def test_existing_multibranch_set_block_gets_the_index_inlined_into_its_selected_branch(environment):
    source = (
        "{% set extra_num='extra'|custom_index %}"
        "{% set is_extra = episode_type == 'aux' or episode_type == 'trailer' %}"
        "{% set plex_ep_id %}"
        "{% if not is_extra %}S{{ season_num }}E{{ ep_num }}"
        "{% elif season == 'test' %}Test"
        "{% else %}extra{{ extra_num }}"
        "{% endif %}"
        "{% endset %}"
        "/downloads/{{ plex_ep_id }}.ext"
    )
    item, = advisory(environment, source).advisories
    suggestion = item.suggestion
    assert suggestion is not None
    assert "{% set extra_num=" not in suggestion.output_template
    assert "{% elif season == 'test' %}" in suggestion.after
    assert "extra{{ 'extra' | custom_index }}" in suggestion.after
    assert not advisory(environment, suggestion.output_template).advisories

    cases = [
        dict(episode_type='ep', season='01', expected_use=False),
        dict(episode_type='aux', season='test', expected_use=False),
        dict(episode_type='aux', season='02', expected_use=True),
    ]
    for case in cases:
        before_used = []
        after_used = []
        values = dict(
            episode_type=case['episode_type'],
            season=case['season'],
            season_num='01',
            ep_num='04',
        )
        before = environment.from_string(source).render(
            **values, resolve=lambda key: before_used.append(key) or 7,
        )
        after = environment.from_string(suggestion.output_template).render(
            **values, resolve=lambda key: after_used.append(key) or 7,
        )
        assert after == before
        assert bool(after_used) == case['expected_use']
        assert before_used == ['extra']


@pytest.mark.parametrize('block', [
    "{% set label %}{{ n }}{% endset %}",  # still unconditional after moving
    "{% set label %}{% if flag %}{{ n }}-{{ n }}{% endif %}{% endset %}",  # multiple uses
])
def test_set_block_advice_stays_conservative_when_moving_the_index_would_not_be_safe(environment, block):
    source = "{% set n='extra'|custom_index %}" + block + "/downloads/{{ label }}.ext"
    item, = advisory(environment, source).advisories
    assert item.suggestion is None


def test_plex_suggestion_uses_existing_condition_and_a_native_set_block(environment):
    result = advisory(environment, PLEX)
    assert result.error is None
    assert len(result.advisories) == 1
    item = result.advisories[0]
    assert item.key == 'extra'
    assert 'every episode' in item.message
    suggestion = item.suggestion
    assert suggestion is not None
    assert suggestion.after == (
        "{% set plex_ep_id %}{% if is_extra %}other{{ 'extra' | custom_index }}"
        "{% else %}S{{ season_num }}E{{ ep_num }}{% endif %}{% endset %}"
    )
    assert '{% set extra_num =' not in suggestion.output_template
    assert "{% set plex_title =" in suggestion.output_template
    assert not advisory(environment, suggestion.output_template).advisories
    counters = defaultdict(int)
    assigned = []
    for kind in ['ep', 'aux', 'ep', 'trailer']:
        used = set()

        def resolve(key):
            if key not in used:
                counters[key] += 1
                used.add(key)
            return counters[key]

        values = dict(season_number='1', episode_number='4', season_type='normal', episode_type=kind,
                      meta_show_year='', show_title='A Show', title='Title', resolve=resolve)
        rendered = environment.from_string(suggestion.output_template).render(values)
        assigned.append(dict(counters) if used else {})
        if kind == 'ep':
            assert 'S01E04' in rendered
    assert assigned == [{}, {'extra': 1}, {}, {'extra': 2}]


@pytest.mark.parametrize('template', [
    "/downloads/{{ 'extra' | custom_index }}.ext",
    "{% set n='extra'|custom_index %}/downloads/{{title}}.ext",
    "{% set n %}{{'extra'|custom_index}}{% endset %}/downloads/{{n}}.ext",
    "/downloads/{% filter upper %}{{'extra'|custom_index}}{% endfilter %}.ext",
    "/downloads/{% for c in title %}{{c}}{% endfor %}{{'extra'|custom_index}}.ext",
    "{% if flag %}/downloads/{{'extra'|custom_index}}.ext{% else %}/downloads/{{'extra'|custom_index}}.ext{% endif %}",
    "{% macro n() %}{{'extra'|custom_index}}{% endmacro %}/downloads/{{n()}}.ext",
    "{% if 'extra'|custom_index > 5 %}/downloads/yes.ext{% else %}/downloads/no.ext{% endif %}",
    "/downloads/{{ ('extra'|custom_index) if true else title }}.ext",
    "/downloads/{{ false or ('extra'|custom_index) }}.ext",
])
def test_guaranteed_calls_warn_even_without_a_safe_refactor(environment, template):
    result = advisory(environment, template)
    assert [item.key for item in result.advisories] == ['extra']
    if result.advisories[0].kind == 'all_episodes':
        assert result.advisories[0].suggestion is None


@pytest.mark.parametrize('template', [
    "/downloads/{{ title }}.ext",
    "{# {{ 'extra'|custom_index }} #}/downloads/{{title}}.ext",
    "/downloads/{% raw %}{{ 'extra'|custom_index }}{% endraw %}.ext",
    "/downloads/{{ 'extra'|custom_index if flag else title }}.ext",
    "/downloads/{{ flag and ('extra'|custom_index) }}.ext",
    "/downloads/{{ flag or ('extra'|custom_index) }}.ext",
    "/downloads/{% for c in title %}{{'extra'|custom_index}}{% endfor %}.ext",
    "{% set n %}{% if flag %}{{'extra'|custom_index}}{% endif %}{% endset %}/downloads/{{n}}.ext",
    "{% macro unused() %}{{'extra'|custom_index}}{% endmacro %}/downloads/fixed.ext",
    "/downloads/{{ true or ('extra'|custom_index) }}.ext",
    "{% if false %}{{'extra'|custom_index}}{% endif %}/downloads/fixed.ext",
    "{% macro wrap() %}no caller{% endmacro %}/downloads/{% call wrap() %}{{'extra'|custom_index}}{% endcall %}.ext",
])
def test_conditional_unknown_or_inert_calls_do_not_claim_every_episode(environment, template):
    assert advisory(environment, template).advisories == ()


def test_unsaved_definitions_are_authoritative_and_each_index_is_separate(environment):
    template = "/downloads/{{'a'|custom_index}}-{{'b'|custom_index}}.ext"
    assert advisory(environment, template, ()).advisories == ()
    result = advisory(environment, template, ('b', 'a', 'unused'))
    assert [item.key for item in result.advisories] == ['a', 'b']
    assert [item.key for item in advisory(environment, template, ('a',)).advisories] == ['a']


@pytest.mark.parametrize('template', ["{% set n = 'extra' | custom_index e%}", "{% if extra %}", '{{'])
def test_incomplete_typing_is_an_expected_advisory_response(environment, template):
    result = advisory(environment, template)
    assert result.advisories == ()
    assert result.error


def test_analysis_never_executes_filters_or_templates(environment):
    calls = []
    environment.filters['observed'] = lambda value: calls.append(value)
    environment.filters['custom_index'] = lambda value: calls.append(value)
    template = "{% set ignored='value'|observed %}{% set n='extra'|custom_index %}/downloads/{{'x' ~ n if flag else 'y'}}.ext"
    assert len(advisory(environment, template).advisories) == 1
    assert calls == []


@pytest.mark.parametrize('middle', [
    "{% set alias = n %}",
    "{% set alias = '%02d'|format(n) %}",
    "{% set tmp = n %}{% set alias = tmp|string %}",
])
def test_single_use_alias_and_format_chains_are_not_plex_specific(environment, middle):
    source = "{% set n='extra'|custom_index %}" + middle + "{% set label = 'bonus-' ~ alias if flag else 'regular' %}/downloads/{{label}}.ext"
    suggestion = advisory(environment, source).advisories[0].suggestion
    assert suggestion is not None
    for flag, value in product([False, True], [1, 7]):
        actual = set()
        def resolve(key):
            actual.add(key)
            return value
        rendered = environment.from_string(suggestion.output_template).render(flag=flag, resolve=resolve)
        expected = environment.from_string(source).render(flag=flag, resolve=lambda key: value)
        assert rendered == expected
        assert bool(actual) == flag


@pytest.mark.parametrize('source', [
    "{% set n='extra'|custom_index %}{% set label='x' ~ n if flag else 'y' %}/downloads/{{label}}-{{n}}.ext",  # multiple use
    "{% set n='extra'|custom_index %}{% set label='x' ~ n if n>5 else 'y' %}/downloads/{{label}}.ext",  # self guard
    "{% set n='extra'|custom_index %}{% set alias=title|random ~ n %}{% set label='x' ~ alias if flag else 'y' %}/downloads/{{label}}.ext",  # nondeterministic computation
    "{% set n='extra'|custom_index %}{% set alias=title ~ n %}{% set title='new' %}{% set label='x' ~ alias if flag else 'y' %}/downloads/{{label}}.ext",  # time-dependent binding
    "{% set n='extra'|custom_index %}{% set label='x' ~ n if flag else 'y' %}/downloads/fixed.ext",  # dead label
    "{% set n='extra'|custom_index %}{% set label='x' ~ n if title.startswith('X') else 'y' %}/downloads/{{label}}.ext",  # unsupported source printer
    "{% set n='extra'|custom_index %}{% with n=99 %}{{n}}{% endwith %}{% set label='x' ~ n if flag else 'y' %}/downloads/{{label}}.ext",  # shadowing
])
def test_ambiguous_replacements_are_omitted_not_guessed(environment, source):
    item, = advisory(environment, source).advisories
    assert item.key == 'extra'
    assert item.suggestion is None


def test_interleaved_code_and_comments_are_preserved(environment):
    template = "{# header #}{% set n='extra'|custom_index %}{# keep #}{% set unrelated='ok' %}{% set id='E' ~ n if flag else 'N' %}/downloads/{{unrelated}}/{{id}}.ext"
    suggestion = advisory(environment, template).advisories[0].suggestion
    assert suggestion is not None
    assert '{# header #}{# keep #}{% set unrelated=\'ok\' %}' in suggestion.output_template


def test_concat_none_stringification_is_preserved(environment):
    template = "{% set n='extra'|custom_index %}{% set label='E' ~ n if flag else 'N' ~ none %}/downloads/{{label}}.ext"
    suggestion = advisory(environment, template).advisories[0].suggestion
    assert suggestion is not None
    assert environment.from_string(suggestion.output_template).render(flag=False, resolve=lambda key: 1) == '/downloads/NNone.ext'


def test_result_has_no_side_effect_on_later_native_rendering(environment):
    original = "{% set n='extra'|custom_index %}{% set label='E' ~ n if flag else 'N' %}/downloads/{{label}}.ext"
    advisory(environment, original)
    calls = []
    output = environment.from_string(original).render(flag=False, resolve=lambda key: calls.append(key) or 3)
    assert output == '/downloads/N.ext'
    assert calls == ['extra']  # advisory did NOT change eager runtime semantics


def test_random_membership_is_not_proposed_through_an_alias(environment):
    template = (
        "{% set flag = [true, false]|random %}{% set n='extra'|custom_index %}"
        "{% set label='X' ~ n if flag else 'normal' %}/downloads/{{label}}.ext"
    )
    item, = advisory(environment, template).advisories
    assert item.suggestion is None


def test_unrelated_rebindings_and_dynamic_jinja_do_not_prevent_a_safe_suggestion(environment):
    template = (
        "{% set unrelated = 'old' %}{% set unrelated = title.upper() %}"
        "{% set n='extra'|custom_index %}"
        "{% set label='X' ~ n if flag else 'normal' %}/downloads/{{unrelated}}/{{label}}.ext"
    )
    item, = advisory(environment, template).advisories
    assert item.suggestion is not None
    assert "{% set unrelated = title.upper() %}" in item.suggestion.output_template


def test_multiple_indexes_offer_separate_independent_suggestions(environment):
    source = (
        "{% set a='alpha'|custom_index %}{% set b='beta'|custom_index %}"
        "{% set x='A' ~ a if is_a else 'N' %}{% set y='B' ~ b if is_b else 'N' %}"
        "/downloads/{{x}}-{{y}}.ext"
    )
    result = advisory(environment, source, ('alpha', 'beta'))
    assert [item.key for item in result.advisories] == ['alpha', 'beta']
    assert all(item.suggestion for item in result.advisories)
    updated = result.advisories[0].suggestion.output_template
    assert [item.key for item in advisory(environment, updated, ('alpha', 'beta')).advisories] == ['beta']


INTENTIONAL_SEQUENCE = (
    "{% set extra_num = 'extra' | custom_index %}"
    "{% set clean_title = title.replace(' ', '-') %}"
    "/downloads/{{ extra_num }} - {{ clean_title }}.ext"
)


def test_unconditional_sequence_recommends_builtin_episode_index(environment):
    item, = advisory(environment, INTENTIONAL_SEQUENCE).advisories
    assert item.kind == 'episode_index'
    assert 'episode_index' in item.message
    assert 'gaps' in item.message
    assert item.suggestion is not None
    assert item.suggestion.after == '{% set extra_num = (episode_index | int) %}'
    assert "{% set clean_title = title.replace(' ', '-') %}" in item.suggestion.output_template
    assert not advisory(environment, item.suggestion.output_template).advisories
    used = []
    result = environment.from_string(item.suggestion.output_template).render(
        title='The Episode', episode_index='42', resolve=lambda key: used.append(key),
    )
    assert result == '/downloads/42 - The-Episode.ext'
    assert used == []


@pytest.mark.parametrize('template', [
    "/downloads/{{'extra'|custom_index}}.ext",
    "{% set n='extra'|custom_index %}{% set alias=n %}/downloads/{{alias}}-{{n}}.ext",
    "{% set n='extra'|custom_index %}{% set label='%03d'|format(n) %}/downloads/{{label}}.ext",
    "{% set n='extra'|custom_index %}/downloads/{{ n + 1 }}.ext",
    "{% set n='extra'|custom_index %}{% if flag %}{% set title='changed' %}{% endif %}/downloads/{{n}}-{{title}}.ext",
    "/downloads/{% for c in title %}{{c}}{% endfor %}{{'extra'|custom_index}}.ext",
    "/downloads/{% filter upper %}{{'extra'|custom_index}}{% endfilter %}.ext",
])
def test_plain_uses_follow_aliases_but_ignore_unrelated_jinja(environment, template):
    item, = advisory(environment, template).advisories
    assert item.kind == 'episode_index'
    assert item.suggestion is not None
    for number in (1, 12, 101):
        values = dict(title='Title', flag=False, episode_index=str(number), resolve=lambda key: number)
        original = environment.from_string(template).render(values)
        changed = environment.from_string(item.suggestion.output_template).render(values)
        assert changed == original


@pytest.mark.parametrize('use', [
    "{% set alias=n %}/downloads/{{alias if flag else 0}}.ext",
    "{% set alias=n %}/downloads/{{flag and alias}}.ext",
    "{% set alias=n %}/downloads/{{flag or alias}}.ext",
    "{% set label='X' ~ n if flag else 'Y' %}/downloads/{{label}}.ext",
    "/downloads/{% if flag %}{{n}}{% else %}normal{% endif %}.ext",
    "/downloads/{% if n > 4 %}large{% else %}small{% endif %}.ext",
    "/downloads/{% for part in title %}{{n}}{% endfor %}.ext",
    "/downloads/{{n}}-{{n if flag else 0}}.ext",
    "{% macro label() %}{{n if flag else 0}}{% endmacro %}/downloads/{{label()}}.ext",
])
def test_conditionally_used_eager_indexes_do_not_get_builtin_recommendation(environment, use):
    item, = advisory(environment, "{% set n='extra'|custom_index %}" + use).advisories
    assert item.kind == 'all_episodes'
    assert 'put the custom_index call inside the condition' in item.message


def test_plex_keeps_existing_conditional_set_block_recommendation(environment):
    item, = advisory(environment, PLEX).advisories
    assert item.kind == 'all_episodes'
    assert item.suggestion is not None
    assert '{% if is_extra %}' in item.suggestion.after
    assert 'episode_index' not in item.suggestion.output_template


@pytest.mark.parametrize('suffix', [
    "/downloads/{{title}}.ext",  # declared but never used
    "{% set n=99 %}/downloads/{{n}}.ext",  # ambiguous rebinding
    "{% with n=99 %}{{n}}{% endwith %}/downloads/{{n}}.ext",  # shadowing
    "/downloads/{{title.replace('x', n)}}.ext",  # opaque index-connected call
])
def test_uncertain_or_unused_values_keep_generic_warning(environment, suffix):
    item, = advisory(environment, "{% set n='extra'|custom_index %}" + suffix).advisories
    assert item.kind == 'all_episodes'


def test_recommendation_and_replacements_are_independent_per_key(environment):
    template = (
        "{% set all='all'|custom_index %}{% set n='extra'|custom_index %}"
        "{% set label='X' ~ n if flag else 'normal' %}/downloads/{{all}}-{{label}}.ext"
    )
    items = advisory(environment, template, ('all', 'extra')).advisories
    assert [(item.key, item.kind) for item in items] == [('all', 'episode_index'), ('extra', 'all_episodes')]
    assert all(item.suggestion for item in items)
    changed = items[0].suggestion.output_template
    assert "'extra'|custom_index" in changed
    remaining = advisory(environment, changed, ('all', 'extra')).advisories
    assert [(item.key, item.kind) for item in remaining] == [('extra', 'all_episodes')]


def test_builtin_replacement_preserves_comments_raw_text_and_other_keys(environment):
    template = (
        "{# 'extra'|custom_index #}"
        "{% set literal=\"'extra'|custom_index\" %}"
        "/downloads/{{'extra'|custom_index}}-{{'other'|custom_index}}"
        "{% raw %}'extra'|custom_index{% endraw %}.ext"
    )
    item, = advisory(environment, template).advisories
    assert item.suggestion is not None
    changed = item.suggestion.output_template
    assert "{# 'extra'|custom_index #}" in changed
    assert '{% set literal="\'extra\'|custom_index" %}' in changed
    assert "{{'other'|custom_index}}" in changed
    assert "{% raw %}'extra'|custom_index{% endraw %}" in changed


@pytest.mark.parametrize('definition', [
    "{% set episode_index=999 %}",
    "{% macro episode_index() %}different{% endmacro %}",
])
def test_shadowed_builtin_retains_recommendation_without_an_unsafe_edit(environment, definition):
    template = definition + "/downloads/{{'extra'|custom_index}}.ext"
    item, = advisory(environment, template).advisories
    assert item.kind == 'episode_index'
    assert item.suggestion is None


def test_unknown_source_locations_do_not_remove_the_builtin_warning(environment):
    template = " \n{%- set n='extra'|custom_index %}/downloads/{{n}}.ext"
    item, = advisory(environment, template).advisories
    assert item.kind == 'episode_index'
    assert item.suggestion is None


def test_unconditional_advice_does_not_execute_any_filters(environment):
    calls = []
    environment.filters['observed'] = lambda value: calls.append(value)
    environment.filters['custom_index'] = lambda value: calls.append(value)
    template = "{% set ignored='value'|observed %}/downloads/{{'extra'|custom_index}}.ext"
    item, = advisory(environment, template).advisories
    assert item.kind == 'episode_index'
    assert item.suggestion is not None
    assert calls == []
