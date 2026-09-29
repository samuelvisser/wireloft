"""Differential tests: same values/types/output, only index demand may differ."""
from itertools import product

import pytest
from jinja2 import StrictUndefined, pass_context
from jinja2.sandbox import ImmutableSandboxedEnvironment

from backend.utils.jinja_analysis.custom_index_advisory import get_custom_index_advisories
from backend.utils.jinja_analysis.custom_index_refactors import suggest_guarded_index


@pytest.fixture
def environment():
    env = ImmutableSandboxedEnvironment(undefined=StrictUndefined, autoescape=False, keep_trailing_newline=True)
    env.globals.clear()
    env.finalize = lambda value: str(value if value is not None else '').replace('/', '_').replace('\\', '_')

    @pass_context
    def index(context, key):
        return context['resolve'](key)
    env.filters['custom_index'] = index
    return env


def suggestion(env, source, key='extra'):
    result = get_custom_index_advisories(source, definition_keys={key}, environment=env)
    assert result.error is None
    item, = result.advisories
    assert item.kind == 'all_episodes'
    assert item.suggestion is not None, source
    return item.suggestion


def render(env, source, values, number):
    used = []
    result = env.from_string(source).render(**values, resolve=lambda key: used.append(key) or number)
    return result, used


EAGER = "{% set n='extra'|custom_index %}"
CASES = [
    (EAGER + "/downloads/{% if flag %}extra{{n}}{% else %}normal{% endif %}.ext", lambda v, n: bool(v['flag'])),
    (EAGER + "/downloads/{% if skip %}trailer{% elif flag %}extra{{n}}{% else %}normal{% endif %}.ext", lambda v, n: not v['skip'] and bool(v['flag'])),
    (EAGER + "/downloads/{% if flag %}{% if skip %}trailer{% else %}extra{{n}}{% endif %}{% endif %}.ext", lambda v, n: v['flag'] and not v['skip']),
    (EAGER + "/downloads/{{ flag and ('extra' ~ n) or normal_id }}.ext", lambda v, n: bool(v['flag'])),
    (EAGER + "/downloads/{{ flag or ('extra' ~ n) }}.ext", lambda v, n: not v['flag']),
    (EAGER + "/downloads/{{ 'T' if skip else ('extra' ~ n if flag else normal_id) }}.ext", lambda v, n: not v['skip'] and bool(v['flag'])),
    (EAGER + "{% set id='T' if skip else ('extra' ~ n if flag else normal_id) %}/downloads/{{id}}.ext", lambda v, n: not v['skip'] and bool(v['flag'])),
    (EAGER + "{% set alias=n %}{% set formatted='%03d'|format(alias) %}/downloads/{{formatted if flag else normal_id}}.ext", lambda v, n: bool(v['flag'])),
    (EAGER + "{% set formatted='extra-%03d'|format(n) %}{% if flag %}{{formatted}}{% endif %}", lambda v, n: bool(v['flag'])),
    (EAGER + "/downloads/{% if flag and n > 5 %}later{% else %}early{% endif %}.ext", lambda v, n: bool(v['flag'])),
    (EAGER + "/downloads/{{ (n + 1) if flag else 0 }}.ext", lambda v, n: bool(v['flag'])),
    (EAGER + "{% set label=n if flag else 0 %}/downloads/{{label + 1}}.ext", lambda v, n: bool(v['flag'])),
    (EAGER + "{% set label='extra' ~ n if flag %}/downloads/{{label|default('missing')}}.ext", lambda v, n: bool(v['flag'])),
    (EAGER + "{% set label='extra' ~ n if flag %}/downloads/{{label is undefined}}.ext", lambda v, n: bool(v['flag'])),
    (EAGER + "{% set label|upper %}{% if flag %}extra{{n}}{% else %}normal{% endif %}{% endset %}/downloads/{{label}}.ext", lambda v, n: bool(v['flag'])),
    (EAGER + "{% set label|length %}{% if flag %}extra{{n}}{% else %}normal{% endif %}{% endset %}/downloads/{{label + 1}}.ext", lambda v, n: bool(v['flag'])),
    (EAGER + "/downloads/{% if flag %}{% filter upper %}extra{{n}}{% endfilter %}{% else %}normal{% endif %}.ext", lambda v, n: bool(v['flag'])),
    (EAGER + "{% macro label() %}{{'extra' ~ n if flag else normal_id}}{% endmacro %}/downloads/{{label()}}.ext", lambda v, n: bool(v['flag'])),
    (EAGER + "{% macro label() %}{{n}}{% endmacro %}/downloads/{{label() if flag else normal_id}}.ext", lambda v, n: bool(v['flag'])),
    ("{% macro label(normal, extra_id, extra) %}{{extra_id if extra else normal}}{% endmacro %}/downloads/{{label(normal_id, 'extra' ~ ('extra'|custom_index), flag)}}.ext", lambda v, n: bool(v['flag'])),
    ("{% macro label(normal, extra_id, extra) %}{{extra_id if extra else normal}}{% endmacro %}/downloads/{{label(extra=flag, normal=normal_id, extra_id='extra' ~ ('extra'|custom_index))}}.ext", lambda v, n: bool(v['flag'])),
    ("{% macro label(normal, num, extra) %}{{'%03d'|format(num) if extra else normal}}{% endmacro %}/downloads/{{label(normal_id, 'extra'|custom_index, flag)}}.ext", lambda v, n: bool(v['flag'])),
    (EAGER + "{% macro label(normal, extra_id, extra) %}{{extra_id if extra else normal}}{% endmacro %}/downloads/{{label(normal_id, 'extra' ~ n, flag)}}.ext", lambda v, n: bool(v['flag'])),
    ("{% set ids=[normal_id, 'extra' ~ ('extra'|custom_index)] %}/downloads/{{ids[1] if flag else ids[0]}}.ext", lambda v, n: bool(v['flag'])),
    ("{% set ids=[normal_id, 'extra' ~ ('extra'|custom_index)] %}/downloads/{{ids[1 if flag else 0]}}.ext", lambda v, n: bool(v['flag'])),
    ("/downloads/{{[normal_id, 'extra' ~ ('extra'|custom_index)][1 if flag else 0]}}.ext", lambda v, n: bool(v['flag'])),
    ("/downloads/{{['S' ~ season_num ~ 'E' ~ ep_num, 'extra' ~ ('extra'|custom_index)][1 if flag else 0]}}.ext", lambda v, n: bool(v['flag'])),
    ("{% set ids={'normal':normal_id, 'extra':'extra' ~ ('extra'|custom_index)} %}/downloads/{{ids['extra'] if flag else ids['normal']}}.ext", lambda v, n: bool(v['flag'])),
    ("{% set ids={'normal':normal_id, 'extra':'extra' ~ ('extra'|custom_index)} %}/downloads/{{ids['extra' if flag else 'normal']}}.ext", lambda v, n: bool(v['flag'])),
    ("{% set yes = flag == true %}{% set ids={true:'extra' ~ ('extra'|custom_index), false:normal_id} %}/downloads/{{ids[yes]}}.ext", lambda v, n: v['flag'] == True),
    (EAGER + "{% set plex_ep_id %}{% if not flag %}S{{season_num}}E{{ep_num}}{% elif skip %}Test{% else %}extra{{n}}{% endif %}{% endset %}/downloads/{{plex_ep_id}}.ext", lambda v, n: bool(v['flag']) and not v['skip']),
]


@pytest.mark.parametrize('source, demand', CASES, ids=[f'pattern-{i+1}' for i in range(len(CASES))])
@pytest.mark.parametrize('number', [1, 7, 25])
def test_shortlist_preserves_native_rendering_and_only_changes_index_demand(environment, source, demand, number):
    change = suggestion(environment, source)
    for flag, skip in product([False, True, '', 'extra', 0, 1, None], [False, True]):
        values = dict(flag=flag, skip=skip, normal_id='S01E02', season_num='01', ep_num='02')
        before, old_calls = render(environment, source, values, number)
        after, calls = render(environment, change.output_template, values, number)
        assert old_calls == ['extra']
        assert after == before, (source, change.output_template, values)
        assert calls == (['extra'] if demand(values, number) else []), (source, values)
    assert not get_custom_index_advisories(change.output_template, definition_keys={'extra'}, environment=environment).advisories


UNSAFE = [
    EAGER + "{% set alias=n|observed %}{{alias if flag else 'normal'}}",
    EAGER + "{% set alias='%q'|format(n) %}{{alias if flag else 'normal'}}",
    EAGER + "{% set alias=title ~ n %}{% set title='new' %}{{alias if flag else 'normal'}}",
    EAGER + "{% set n=12 %}{{n if flag else 0}}",
    EAGER + "{% macro m(n) %}{{n if flag else 0}}{% endmacro %}{{m(9)}}",
    EAGER + "{% set gate=[true,false]|random %}{{n if gate else 0}}",
    EAGER + "{% set gate='other'|custom_index %}{{n if gate else 0}}",
    EAGER + "{% set gate=title.startswith('X') %}{{n if gate else 0}}",  # opaque predicates stay conservative
    EAGER + "{{n if flag else 0}}-{{n}}",
    EAGER + "{% macro m() %}{{n if flag else 0}}{% endmacro %}{{m()}}{{m()}}",
    "{% macro m(a,gate) %}{{a if gate else 0}}{% endmacro %}{{m('extra'|custom_index,[true,false]|random)}}",
    "{% macro m(a,gate) %}{{a if gate else 0}}{% endmacro %}{{m('extra'|custom_index,flag)}}{{m.arguments}}",
    "{% macro m(a,gate) %}{{a if gate else 0}}{{a}}{% endmacro %}{{m('extra'|custom_index,flag)}}",
    "{% macro m(a,gate) %}{{a if gate else 0}}{% endmacro %}{{m(('extra'|custom_index)|observed,flag)}}",
    "{% set ids=['normal','extra'|custom_index] %}{{ids}}/{{ids[1] if flag else ids[0]}}",
    "{% set ids=['normal','extra'|custom_index] %}{{ids[index]}}",
    "{% set ids=['normal','extra'|custom_index] %}{{ids[1] if flag else ids[12]}}",
    "{% set ids={'x':'extra'|custom_index,'x':'normal'} %}{{ids['x'] if flag else 'normal'}}",
    "{% set ids=['normal', ('extra'|custom_index)|observed] %}{{ids[1] if flag else ids[0]}}",
    "{{['normal'|observed, 'extra'|custom_index][1 if flag else 0]}}",  # cannot suppress the other eager evaluation
    "{% if flag %}{{n}}{% endif %}" + EAGER,
    "{% macro m() %}{{n if flag else 0}}{% endmacro %}" + EAGER + "{{m()}}",  # late closure binding
    EAGER + "{% set dead='x'~n if flag else 'normal' %}/downloads/fixed.ext",
    EAGER + "{% include 'other' %}{{n if flag else 0}}",
    " \n{%- set n='extra'|custom_index %}{{n if flag else 0}}",
]


@pytest.mark.parametrize('source', UNSAFE)
def test_uncertainty_leaves_the_warning_without_replacement(environment, source):
    environment.filters['observed'] = lambda value: value
    result = get_custom_index_advisories(source, definition_keys={'extra'}, environment=environment)
    item, = result.advisories
    assert item.suggestion is None, (source, item.suggestion)


def test_static_advice_never_compiles_executes_or_samples_user_code(environment, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('advisory executed user code')
    monkeypatch.setattr(environment, 'compile', forbidden)
    monkeypatch.setattr(environment, 'from_string', forbidden)
    environment.filters['observed'] = forbidden
    for source, _ in CASES:
        source = "{% set untouched=title|observed %}" + source
        assert suggestion(environment, source)


def test_named_table_keeps_non_index_entry_side_effects_and_evaluation_count(environment):
    trace = []
    @pass_context
    def observed(context, value):
        trace.append(value)
        return value
    environment.filters['observed'] = observed
    source = "{% set ids=[title|observed, 'extra' ~ ('extra'|custom_index)] %}{{ids[1] if flag else ids[0]}}"
    change = suggestion(environment, source)
    for flag in (False, True):
        trace.clear()
        before, _ = render(environment, source, {'flag':flag,'title':'Title'}, 7)
        expected = trace[:]
        trace.clear()
        after, calls = render(environment, change.output_template, {'flag':flag,'title':'Title'}, 7)
        assert after == before
        assert trace == expected == ['Title']
        assert calls == (['extra'] if flag else [])


def test_unrelated_calls_comments_raw_text_and_original_jinja_control_flow_are_kept(environment):
    source = (
        "{# 'extra'|custom_index #}{% set clean_title=title.replace(' ', '-') %}"
        + EAGER + "{% if skip %}Trailer{% elif flag %}{{n}}{% else %}Normal{% endif %}"
        "{% raw %}{{n}}{% endraw %}/{{clean_title}}"
    )
    change = suggestion(environment, source)
    for unchanged in ["{# 'extra'|custom_index #}", "{% set clean_title=title.replace(' ', '-') %}",
                      '{% if skip %}Trailer{% elif flag %}', '{% else %}Normal{% endif %}',
                      '{% raw %}{{n}}{% endraw %}']:
        assert unchanged in change.output_template


def test_other_index_definitions_and_calls_are_not_rewritten(environment):
    source = "{% set other='other'|custom_index %}" + EAGER + "{{other}}-{{n if flag else 'normal'}}"
    change = suggestion(environment, source)
    assert "{% set other='other'|custom_index %}" in change.output_template
    for flag in (False, True):
        output, calls = render(environment, change.output_template, {'flag':flag}, 7)
        assert output == ('7-7' if flag else '7-normal')
        assert calls == (['other', 'extra'] if flag else ['other'])


def test_no_else_refactor_retains_undefined_default_and_type_behavior(environment):
    source = EAGER + "{% set label=n if flag %}{{label is undefined}}/{{label|default('missing')}}"
    change = suggestion(environment, source)
    for flag in (False, True):
        before, _ = render(environment, source, {'flag':flag}, 7)
        after, calls = render(environment, change.output_template, {'flag':flag}, 7)
        assert after == before
        assert calls == (['extra'] if flag else [])


def test_capture_prettification_is_not_used_before_a_value_sensitive_filter(environment):
    source = EAGER + "{% set label='extra' ~ n if flag else title %}{{label|replace('/', '-')}}"
    change = suggestion(environment, source)
    for flag in (False, True):
        values = {'flag':flag, 'title':'A/B'}
        assert render(environment, change.output_template, values, 7)[0] == render(environment, source, values, 7)[0]
    assert "{% set label %}" not in change.output_template


def test_named_table_preserves_failures_in_unselected_non_index_entries(environment):
    @pass_context
    def fail(context, value):
        raise ValueError('unrelated failure must still happen')
    environment.filters['observed'] = fail
    source = "{% set ids=[title|observed, 'extra'|custom_index] %}{{ids[1] if flag else ids[0]}}"
    change = suggestion(environment, source)
    for candidate in (source, change.output_template):
        with pytest.raises(ValueError, match='unrelated failure'):
            render(environment, candidate, {'flag':True,'title':'Title'}, 7)


def test_chained_macro_parameters_with_rebound_or_shared_arguments_are_omitted(environment):
    source = EAGER + "{% macro m(extra, gate) %}{{extra if gate else 'normal'}}{% endmacro %}{{m(n,flag)}}-{{n}}"
    item, = get_custom_index_advisories(source, definition_keys={'extra'}, environment=environment).advisories
    assert item.suggestion is None
