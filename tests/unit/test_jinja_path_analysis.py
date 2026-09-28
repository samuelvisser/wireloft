from __future__ import annotations

from itertools import product
import re

from jinja2 import StrictUndefined, nodes
from jinja2.sandbox import ImmutableSandboxedEnvironment
import pytest

from backend.utils.jinja_analysis import UnknownOutput, analyze_template, expression_dependencies
from backend.utils.jinja_analysis.comparison import OutputOverlap, compare_outputs
from backend.utils.jinja_analysis.expressions import analysis_environment
from backend.utils.jinja_analysis.paths import INPUT_PREFIX


def _emit(value):
    return ''.join(c for c in str(value if value is not None else '').replace('/', '_').replace('\\', '_') if ord(c) >= 32)


@pytest.fixture
def environment():
    environment = ImmutableSandboxedEnvironment(autoescape=False, undefined=StrictUndefined)
    environment.globals.clear()
    environment.finalize = _emit
    return environment


def _compare(left, right, environment, **kwargs):
    return compare_outputs(
        analyze_template(left, environment=environment, namespace='left'),
        analyze_template(right, environment=environment, namespace='right'),
        environment=environment, **kwargs,
    ).status


@pytest.mark.parametrize(('left', 'right'), [
    ('/downloads/{{ title }}.ext', '{% set name = title %}/downloads/{{ name }}.ext'),
    ('/downloads/{{ title }}.ext', '{% set a = title %}{% set b = a %}/downloads/{{ b }}.ext'),
    ('/downloads/{{ title }} - {{ number }}.ext', "/downloads/{{ title ~ ' - ' ~ number }}.ext"),
    ('/downloads/{{ title|upper }}.ext', '{% with name = title %}/downloads/{{ name|upper }}.ext{% endwith %}'),
    ('/downloads/{{ title|upper }}.ext', '{% macro label(value) %}{{ value|upper }}{% endmacro %}/downloads/{{ label(title) }}.ext'),
    ('/downloads/{{ title }}.ext', '{% set name %}{{ title }}{% endset %}/downloads/{{ name }}.ext'),
    ('/downloads/X{{ title }}.ext', '{% set name %}X{{ title }}{% endset %}/downloads/{{ name }}.ext'),
    ('/downloads/{{ title }}.ext', '{% if false %}/other/{{ title }}.ext{% else %}/downloads/{{ title }}.ext{% endif %}'),
    ('/downloads/LIBRARY/{{ title }}.ext', "/downloads/{{ 'library'|upper }}/{{ title }}.ext"),
    ('/downloads/a/b/{{ title }}.ext', "/downloads/{% for folder in ['a', 'b'] %}{{ folder }}/{% endfor %}{{ title }}.ext"),
    ('/downloads/1/2/{{ title }}.ext', "/downloads/{% for folder in ['a', 'b'] %}{{ loop.index }}/{% endfor %}{{ title }}.ext"),
    ('/downloads/aux/{{ title }}.ext', "{% if kind == 'aux' %}/downloads/{{ kind }}/{{ title }}.ext{% else %}/other/{{ title }}.ext{% endif %}"),
    ('/downloads/a/{{ title }}.ext', "/downloads/{{ 'a' if flag else 'b' }}/{{ title }}.ext"),
    ('/downloads/A/{{ title }}.ext', "/downloads/{{ ('a' if flag else 'b')|upper }}/{{ title }}.ext"),
])
def test_equivalent_outputs(environment, left, right):
    assert _compare(left, right, environment) == OutputOverlap.OVERLAP


@pytest.mark.parametrize(('left', 'right'), [
    ('/downloads/a/{{ title }}.ext', '/downloads/b/{{ title }}.ext'),
    ('/downloads/{{ title }}-a.ext', '/downloads/{{ title }}-b.ext'),
    ("{% if kind == 'aux' %}/same/{{ title }}.ext{% else %}/left/{{ title }}.ext{% endif %}",
     "{% if kind != 'aux' %}/same/{{ title }}.ext{% else %}/right/{{ title }}.ext{% endif %}"),
    ("{% if kind in ['aux', 'trailer'] %}/same/{{ title }}.ext{% else %}/left/{{ title }}.ext{% endif %}",
     "{% if kind == 'ep' %}/same/{{ title }}.ext{% else %}/right/{{ title }}.ext{% endif %}"),
    ('{% if a and b %}/same/{{ title }}.ext{% else %}/left/{{ title }}.ext{% endif %}',
     '{% if not a or not b %}/same/{{ title }}.ext{% else %}/right/{{ title }}.ext{% endif %}'),
    ("{% if kind == 'aux' %}/left/{{ title }}.ext{% elif kind == 'ep' %}/same/{{ title }}.ext{% else %}/left2/{{ title }}.ext{% endif %}",
     "{% if kind != 'ep' %}/same/{{ title }}.ext{% else %}/right/{{ title }}.ext{% endif %}"),
    ('{% if year|int < 2020 %}/same/{{ title }}.ext{% else %}/left/{{ title }}.ext{% endif %}',
     '{% if year|int >= 2020 %}/same/{{ title }}.ext{% else %}/right/{{ title }}.ext{% endif %}'),
    ('{% if year|int > 2020 %}/same.ext{% else %}/left.ext{% endif %}',
     '{% if year == "2019" %}/same.ext{% else %}/right.ext{% endif %}'),
])
def test_nonoverlapping_branches(environment, left, right):
    assert _compare(left, right, environment) == OutputOverlap.DISJOINT


def _eval(expression, environment, values):
    ast = nodes.Template([nodes.Assign(nodes.Name('result', 'store'), expression)]).set_lineno(1).set_environment(environment)
    return environment.from_string(ast).make_module(values).result


@pytest.mark.parametrize('template', [
    "{% set a = title %}{% set title = 'changed' %}/downloads/{{ a }}/{{ title }}.ext",
    "{% with title = 'inside' %}/downloads/{{ title }}/{% endwith %}{{ title }}.ext",
    "{% set a = 'outer' %}{% with a = 'inner', b = a %}/downloads/{{ a }}/{{ b }}/{% endwith %}{{ a }}.ext",
    "{% set name %}{{ title }}/extra{% endset %}/downloads/{{ name }}.ext",
    "{% set name %}{{ title }}/extra{% endset %}/downloads/{{ name|replace('/', '-') }}.ext",
    "{% set name|upper %}{{ title }}{% endset %}/downloads/{{ name }}.ext",
    "{% macro label(x, y=x) %}{{ x }}-{{ y }}{% endmacro %}/downloads/{{ label(title) }}.ext",
    "{% set a = 'outer' %}/downloads/{% for x in [1,2] %}{% set a = x %}{{ a }}/{% endfor %}{{ a }}.ext",
    "{% set a='outer' %}{% for x in [] %}x{% else %}{% set a='inner' %}{% endfor %}/downloads/{{a}}.ext",
    "{% set label = 'a' if flag else 'b' %}/downloads/{{ label|upper }}/{{ title }}.ext",
    "{% if kind == 'aux' %}{% set label = 'A' %}{% elif kind == 'ep' %}{% set label = 'E' %}{% else %}{% set label = 'O' %}{% endif %}/downloads/{{ label }}/{{ title }}.ext",
    "{% set a, b = title, kind %}/downloads/{{ a }}-{{ b }}.ext",
    "/downloads/{% for k,v in [('a',1),('b',2)] %}{{k}}-{{v}}/{% endfor %}{{title}}.ext",
    "{% macro label(x) %}{{x}}{% endmacro %}/downloads/{{label(title)}}-{{label(kind)}}.ext",
    "{% set suffix = ' (' ~ kind ~ ')' if flag %}/downloads/{{ title }}{{ suffix }}.ext",
    "{% set label = 'A' if flag %}{% if label %}/downloads/{{ label }}/{{ title }}.ext{% else %}/downloads/{{ title }}.ext{% endif %}",
    "{% set label = 'A' if flag %}/downloads/{{ label|default('fallback') }}/{{ title }}.ext",
    "{% set label = 'A' if flag %}/downloads/{{ 'missing' if label is undefined else label }}/{{ title }}.ext",
])
def test_symbolic_paths_agree_with_real_jinja(environment, template):
    analysis = analyze_template(template, environment=environment)
    assert analysis.complete, analysis.reason
    evaluator = analysis_environment(environment)
    for flag, kind, title in product([False, True], ['aux', 'ep', 'trailer'], ['Hello', 'a/b']):
        real_values = dict(flag=flag, kind=kind, title=title)
        symbolic_values = {INPUT_PREFIX + key: value for key, value in real_values.items()}
        actual = environment.from_string(template).render(real_values)
        matches = []
        for variant in analysis.variants:
            if all(bool(_eval(c.expression, evaluator, symbolic_values)) == c.truth for c in variant.conditions):
                ast = nodes.Template([nodes.Output([nodes.TemplateData(part) if isinstance(part, str) else part
                                                   for part in variant.parts])]).set_lineno(1).set_environment(evaluator)
                matches.append(evaluator.from_string(ast).render(symbolic_values))
        assert matches == [actual], (template, real_values, actual, matches)


def test_known_values_preserve_dependency_provenance(environment):
    result = analyze_template('/downloads/{{ show_title|upper }}/{{ title }}.ext', environment=environment,
                              known_values={'show_title': 'My Show'})
    expr = result.variants[0].parts[1]
    assert isinstance(expr, nodes.Const)
    assert expr.value == 'MY SHOW'
    assert expression_dependencies(expr) == frozenset({'show_title'})


@pytest.mark.parametrize('template', [
    '/downloads/{% for x in title %}{{x}}{% endfor %}.ext',
    "{% macro m(x) %}{{m(x)}}{% endmacro %}/downloads/{{m(title)}}.ext",
    '{% include "external" %}',
    '{% set a = title %}' + '{% set a = a ~ a %}' * 20 + '/downloads/{{ a }}.ext',
])
def test_unsupported_is_unknown_not_safe(environment, template):
    lhs = analyze_template(template, environment=environment)
    rhs = analyze_template('/downloads/{{title}}.ext', environment=environment)
    assert not lhs.complete
    assert lhs.reason
    assert compare_outputs(lhs, rhs, environment=environment).status == OutputOverlap.UNKNOWN


def test_branch_and_work_limits(environment):
    template = '/downloads/' + ''.join('{% if v'+str(i)+' %}a{% else %}b{% endif %}' for i in range(20)) + '.ext'
    result = analyze_template(template, environment=environment, max_variants=8)
    assert not result.complete
    assert len(result.variants) <= 8
    result = analyze_template('/downloads/{{show}}/' + template, environment=environment, max_steps=30)
    assert not result.complete
    assert any(isinstance(part, UnknownOutput) for variant in result.variants for part in variant.parts)


def test_constant_index_filter_is_never_called(environment):
    calls = []
    environment.filters['custom_index'] = lambda key: calls.append(key) or 5
    result = analyze_template("{% set x = 'extras'|custom_index %}/downloads/{{ x }}.ext", environment=environment)
    assert result.complete
    assert calls == []


def test_random_does_not_become_a_false_proof(environment):
    assert _compare('/downloads/{{ title|random }}.ext', '/downloads/{{ title|random }}.ext', environment) == OutputOverlap.UNKNOWN


def test_finalization_happens_after_filters(environment):
    assert _compare("/downloads/{{'a/b'|replace('/', '-')}}.ext", '/downloads/a-b.ext', environment) == OutputOverlap.OVERLAP


def test_filename_policy_is_applied_after_expression_assembly(environment):
    def sanitize(path):
        return '/'.join(re.sub(r'[<>:"\\|?*]', '_', part).rstrip(' .') for part in path.split('/'))
    assert _compare('/downloads/Foo:Bar/{{ title }}.ext', '/downloads/Foo?Bar/{{ title }}.ext', environment,
                    finalize_left=sanitize, finalize_right=sanitize) == OutputOverlap.OVERLAP


def test_empty_symbol_does_not_prove_different_directory_depths(environment):
    assert _compare('/downloads/{{ date }}/file.ext', '/downloads/file.ext', environment) == OutputOverlap.UNKNOWN


def test_literal_marker_text_cannot_impersonate_a_symbol(environment):
    assert _compare('/downloads/{{ title }}.ext', '/downloads/{{ "WLJINJASYMBOL0END" }}.ext', environment) == OutputOverlap.UNKNOWN


def test_analysis_input_names_cannot_be_shadowed_by_template_locals(environment):
    left = "{% set __wireloft_input_title='wrong' %}{% set x=title %}/downloads/{{ 'a' if flag else 'b' }}/{{x}}.ext"
    right = "/downloads/{{ 'a' if flag else 'b' }}/{{title}}.ext"
    assert _compare(left, right, environment) == OutputOverlap.OVERLAP


def test_shadowed_macro_free_variable_is_not_interpreted_in_callers_scope(environment):
    template = "{% set x='outer' %}{% macro m() %}{{x}}{% endmacro %}{% with x='inner' %}/downloads/{{m()}}.ext{% endwith %}"
    assert environment.from_string(template).render() == '/downloads/outer.ext'
    assert not analyze_template(template, environment=environment).complete
    assert _compare(template, '/downloads/inner.ext', environment) == OutputOverlap.UNKNOWN


def test_constant_none_inside_concat_uses_jinja_stringification(environment):
    assert _compare('/downloads/{{ title ~ none }}.ext', '/downloads/{{ title }}None.ext', environment) == OutputOverlap.OVERLAP
    assert _compare('/downloads/{{ title ~ none }}.ext', '/downloads/{{ title }}.ext', environment) != OutputOverlap.OVERLAP


def test_large_constant_operations_are_bounded_before_evaluation(environment):
    for value in ("'x' * 1000000000", '10 ** 1000000000'):
        assert not analyze_template('/downloads/{{ '+value+' }}.ext', environment=environment).complete


def test_custom_index_reachability_ignores_unrelated_output_changes(environment):
    from backend.utils.jinja_analysis import (
        CustomIndexReachabilityStatus,
        compare_custom_index_reachability,
    )

    saved = (
        "{% if kind == 'aux' %}{% set n = 'extras' | custom_index %}"
        "{% else %}{% set n = '' %}{% endif %}"
        "/downloads/{{ n }}-{{ title }}.ext"
    )
    draft = saved.replace("/downloads/", "/downloads/renamed/")
    result = compare_custom_index_reachability(
        saved,
        draft,
        environment=environment,
        keys={"extras"},
    )
    assert result.status == CustomIndexReachabilityStatus.UNCHANGED
    assert result.dependencies == {"kind"}


def test_custom_index_reachability_detects_assignment_condition_change(environment):
    from backend.utils.jinja_analysis import (
        CustomIndexReachabilityStatus,
        compare_custom_index_reachability,
    )

    saved = (
        "{% if kind == 'aux' %}{% set n = 'extras' | custom_index %}"
        "{% else %}{% set n = '' %}{% endif %}/downloads/{{ n }}.ext"
    )
    draft = saved.replace("kind == 'aux'", "kind != 'ep'")
    result = compare_custom_index_reachability(
        saved,
        draft,
        environment=environment,
        keys={"extras"},
    )
    assert result.status == CustomIndexReachabilityStatus.CHANGED


def test_custom_index_reachability_is_unknown_for_short_circuit_effects(environment):
    from backend.utils.jinja_analysis import (
        CustomIndexReachabilityStatus,
        compare_custom_index_reachability,
    )

    template = "/downloads/{{ flag and ('extras' | custom_index) }}.ext"
    result = compare_custom_index_reachability(
        template,
        template,
        environment=environment,
        keys={"extras"},
    )
    assert result.status == CustomIndexReachabilityStatus.UNKNOWN


def test_inline_conditional_without_else_matches_explicit_empty_output(environment):
    implicit = "{% set suffix = ' (' ~ kind ~ ')' if flag %}/downloads/{{ title }}{{ suffix }}.ext"
    explicit = "{% set suffix = ' (' ~ kind ~ ')' if flag else '' %}/downloads/{{ title }}{{ suffix }}.ext"
    assert _compare(implicit, explicit, environment) == OutputOverlap.OVERLAP


def test_inline_conditional_without_else_uses_standard_undefined_under_strict_environment(environment):
    template = (
        "{% set value = 'present' if flag %}"
        "/downloads/{{ value|default('fallback') }}/"
        "{{ 'undefined' if value is undefined else value }}.ext"
    )
    assert environment.from_string(template).render(flag=False) == "/downloads/fallback/undefined.ext"

    analysis = analyze_template(template, environment=environment)
    assert analysis.complete, analysis.reason
    expected = (
        "{% if flag %}/downloads/present/present.ext"
        "{% else %}/downloads/fallback/undefined.ext{% endif %}"
    )
    assert compare_outputs(
        analysis,
        analyze_template(expected, environment=environment),
        environment=environment,
    ).status == OutputOverlap.OVERLAP


def test_inline_conditional_without_else_does_not_coerce_undefined_to_empty_for_operations(environment):
    implicit = "{% set value = 1 if flag %}/downloads/{{ value + 1 }}.ext"
    analysis = analyze_template(
        implicit,
        environment=environment,
        known_values={"flag": False},
    )
    empty_output = analyze_template("/downloads/.ext", environment=environment)
    assert compare_outputs(
        analysis,
        empty_output,
        environment=environment,
    ).status == OutputOverlap.UNKNOWN


def test_internal_undefined_filter_cannot_be_used_by_source_templates(environment):
    result = analyze_template(
        "/downloads/{{ none | __wireloft_analysis_undefined }}.ext",
        environment=environment,
    )
    assert not result.complete
    assert result.reason == "An internal analysis filter cannot be used in source templates"
