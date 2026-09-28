"""Path-sensitive symbolic output using Jinja's parser and expression semantics.

No sample data is rendered, and no media/index lookups are performed. Expressions
are retained as Jinja nodes; only constants are evaluated by Jinja. Unsupported
constructs and resource limits return an explicit incomplete analysis.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field, replace

from jinja2 import Environment, TemplateError, nodes
from jinja2.visitor import NodeTransformer

from .conditions import Conditions, assume
from .expressions import (
    INTERNAL_FILTERS,
    ExpressionAnalysisLimit,
    analysis_environment,
    emitted_expression,
    expression_dependencies,
    expression_key,
    jinja_undefined_expression,
    normalize_expression,
)

INPUT_PREFIX = "__wireloft_input_"


@dataclass(frozen=True)
class UnknownOutput:
    reason: str


@dataclass(frozen=True)
class OutputVariant:
    parts: tuple[str | nodes.Expr | UnknownOutput, ...]
    conditions: Conditions = ()


@dataclass(frozen=True)
class TemplateAnalysis:
    variants: tuple[OutputVariant, ...]
    complete: bool = True
    reason: str | None = None


@dataclass(frozen=True)
class _Macro:
    node: nodes.Macro
    bindings: Mapping[str, nodes.Expr]


@dataclass
class _State:
    bindings: dict[str, nodes.Expr]
    macros: dict[str, _Macro] = field(default_factory=dict)
    parts: tuple[str | nodes.Expr | UnknownOutput, ...] = ()
    conditions: Conditions = ()


class _IncompleteAnalysis(Exception):
    pass


class _ReplaceNode(NodeTransformer):
    def __init__(self, target: nodes.Node, value: nodes.Node):
        self.target, self.value = target, value

    def visit(self, node, *args, **kwargs):
        if node is self.target:
            return deepcopy(self.value)
        return super().visit(node, *args, **kwargs)


def _replace_node(root: nodes.Expr, target: nodes.Expr, value: nodes.Expr) -> nodes.Expr:
    # The source belongs to a private expression copy, never the cached parse.
    return _ReplaceNode(target, value).visit(root)


class _Analyzer:
    def __init__(self, environment: Environment, max_variants: int, max_steps: int, namespace: str):
        self.environment = analysis_environment(environment)
        self.max_variants = max_variants
        self.steps = max_steps
        self.namespace = namespace
        self.call_stack: list[str] = []

    def _step(self) -> None:
        self.steps -= 1
        if self.steps < 0:
            raise _IncompleteAnalysis("Jinja analysis reached its work limit")

    def _bounded(self, values: Iterable) -> list:
        result = []
        for value in values:
            self._step()
            result.append(value)
            if len(result) > self.max_variants:
                raise _IncompleteAnalysis("Jinja analysis reached its branch limit")
        return result

    def expression(self, expression: nodes.Expr, state: _State):
        self._step()
        expression = normalize_expression(expression, state.bindings, self.environment)
        # Expand an inline conditional even when nested in a filter or concat.
        inline = next((node for node in (expression, *expression.find_all(nodes.CondExpr))
                       if isinstance(node, nodes.CondExpr)), None)
        if inline is not None:
            false_value = (
                inline.expr2
                if inline.expr2 is not None
                else jinja_undefined_expression(lineno=inline.lineno)
            )
            for truth, value in ((True, inline.expr1), (False, false_value)):
                for conditions in self._bounded(assume(state.conditions, inline.test, truth)):
                    # Replacement identities must belong to the same private tree.
                    candidate = deepcopy(expression)
                    target = next(node for node in (candidate, *candidate.find_all(nodes.CondExpr))
                                  if isinstance(node, nodes.CondExpr))
                    candidate = _replace_node(candidate, target, value)
                    yield from self.expression(candidate, replace(state, conditions=conditions))
            return
        macro_call = next((node for node in (expression, *expression.find_all(nodes.Call))
                           if isinstance(node, nodes.Call) and isinstance(node.node, nodes.Name)
                           and node.node.name in state.macros), None)
        if macro_call is not None:
            definition = state.macros[macro_call.node.name]
            macro = definition.node
            local_names = {arg.name for arg in macro.args} | {
                node.name for node in macro.find_all(nodes.Name) if node.ctx == "store"
            }
            free_names = {
                node.name for node in macro.find_all(nodes.Name)
                if node.ctx == "load" and node.name not in local_names and node.name not in state.macros
            }
            for name in free_names:
                before = normalize_expression(nodes.Name(name, "load"), definition.bindings, self.environment)
                after = normalize_expression(nodes.Name(name, "load"), state.bindings, self.environment)
                if expression_key(before) != expression_key(after):
                    # Jinja macros close over their defining scope. Do not replace
                    # a captured name with a shadowing with/loop/call-site value.
                    raise _IncompleteAnalysis("Macro free variables changed scope or binding")
            if macro.name in self.call_stack or len(self.call_stack) >= 8:
                raise _IncompleteAnalysis("Recursive macros are not statically expanded")
            if macro_call.dyn_args is not None or macro_call.dyn_kwargs is not None:
                raise _IncompleteAnalysis("Dynamic macro arguments are not statically expanded")
            names = [arg.name for arg in macro.args]
            arguments = dict(zip(names, macro_call.args))
            if len(macro_call.args) > len(names):
                raise _IncompleteAnalysis("Macro has unsupported variable arguments")
            for keyword in macro_call.kwargs:
                if keyword.key not in names or keyword.key in arguments:
                    raise _IncompleteAnalysis("Macro has invalid or unsupported arguments")
                arguments[keyword.key] = keyword.value
            defaults = dict(zip(names[len(names) - len(macro.defaults):], macro.defaults))
            frame = dict(state.bindings)
            for name in names:
                value = arguments.get(name, defaults.get(name))
                if value is None:
                    raise _IncompleteAnalysis("Macro has an unbound parameter")
                frame[name] = normalize_expression(value, state.bindings if name in arguments else frame, self.environment)
            self.call_stack.append(macro.name)
            try:
                captured = self.body(macro.body, [replace(state, bindings=frame, parts=())])
            finally:
                self.call_stack.pop()
            for result in captured:
                value = self._capture(result.parts)
                candidate = deepcopy(expression)
                target = next(node for node in (candidate, *candidate.find_all(nodes.Call))
                              if isinstance(node, nodes.Call) and isinstance(node.node, nodes.Name)
                              and node.node.name == macro.name)
                candidate = _replace_node(candidate, target, value)
                yield from self.expression(candidate, replace(state, conditions=result.conditions))
            return
        yield expression, state

    @staticmethod
    def _capture(parts: tuple[str | nodes.Expr | UnknownOutput, ...]) -> nodes.Expr:
        if any(isinstance(part, UnknownOutput) for part in parts):
            raise _IncompleteAnalysis("Captured output could not be analyzed")
        return nodes.Concat([
            nodes.Const(part) if isinstance(part, str) else emitted_expression(part)
            for part in parts
        ])

    @staticmethod
    def _bind(bindings: dict[str, nodes.Expr], target: nodes.Expr, value: nodes.Expr) -> dict[str, nodes.Expr]:
        result = dict(bindings)
        if isinstance(target, nodes.Name):
            result[target.name] = value
        elif isinstance(target, nodes.Tuple) and isinstance(value, (nodes.Tuple, nodes.List)):
            if len(target.items) != len(value.items):
                raise _IncompleteAnalysis("Tuple assignment cannot be resolved")
            for item, member in zip(target.items, value.items, strict=True):
                result = _Analyzer._bind(result, item, member)
        elif isinstance(target, nodes.Tuple) and isinstance(value, nodes.Const) and isinstance(value.value, (tuple, list)):
            return _Analyzer._bind(result, target, nodes.Tuple([nodes.Const(v) for v in value.value], "load"))
        else:
            raise _IncompleteAnalysis("Namespace/dynamic assignments are not statically expanded")
        return result

    def body(self, body: list[nodes.Stmt], states: list[_State]) -> list[_State]:
        for statement in body:
            next_states = []
            for state in states:
                if any(isinstance(part, UnknownOutput) for part in state.parts):
                    next_states.append(state)
                    continue
                try:
                    results = self._bounded(self.statement(statement, state))
                    if len(next_states) + len(results) > self.max_variants:
                        return [replace(original, parts=(*original.parts, UnknownOutput(
                            "Jinja analysis reached its branch limit"))) for original in states]
                    next_states.extend(results)
                except (_IncompleteAnalysis, ExpressionAnalysisLimit) as exc:
                    # Keep the proven prefix, but do not examine later output
                    # using potentially invalid bindings from this construct.
                    next_states.append(replace(state, parts=(*state.parts, UnknownOutput(str(exc)))))
            states = next_states
        return states

    def statement(self, statement: nodes.Stmt, state: _State):
        self._step()
        if isinstance(statement, nodes.Output):
            current = [state]
            for node in statement.nodes:
                if isinstance(node, nodes.TemplateData):
                    current = [replace(item, parts=(*item.parts, node.data)) for item in current]
                else:
                    current = self._bounded(
                        replace(item, parts=(*item.parts, value))
                        for original in current for value, item in self.expression(node, original)
                    )
            yield from current
        elif isinstance(statement, nodes.Assign):
            for value, result in self.expression(statement.node, state):
                yield replace(result, bindings=self._bind(result.bindings, statement.target, value))
        elif isinstance(statement, nodes.AssignBlock):
            for result in self.body(statement.body, [replace(state, bindings=dict(state.bindings), parts=())]):
                value = self._capture(result.parts)
                if statement.filter is not None:
                    filter_node = deepcopy(statement.filter)
                    # The innermost filter's input is implicit for block filters.
                    inner = filter_node
                    while isinstance(inner.node, nodes.Filter):
                        inner = inner.node
                    inner.node = value
                    value = filter_node
                yield replace(state, conditions=result.conditions,
                              bindings=self._bind(state.bindings, statement.target, value))
        elif isinstance(statement, nodes.If):
            remaining = [state]
            for branch in [statement, *statement.elif_]:
                rejected = []
                for original in remaining:
                    for test, result in self.expression(branch.test, original):
                        accepted = [replace(result, conditions=condition)
                                    for condition in self._bounded(assume(result.conditions, test, True))]
                        yield from self.body(branch.body, accepted)
                        rejected.extend(replace(result, conditions=condition)
                                        for condition in self._bounded(assume(result.conditions, test, False)))
                remaining = self._bounded(rejected)
            yield from self.body(statement.else_, remaining)
        elif isinstance(statement, nodes.With):
            frames = [(state, [])]
            # RHS expressions all see the outer frame, as in Jinja's with scope.
            for value in statement.values:
                frames = self._bounded((result, [*values, expr]) for original, values in frames
                                       for expr, result in self.expression(value, original))
            for original, values in frames:
                bindings = original.bindings
                for target, value in zip(statement.targets, values, strict=True):
                    bindings = self._bind(bindings, target, value)
                for result in self.body(statement.body, [replace(original, bindings=bindings)]):
                    yield replace(result, bindings=state.bindings, macros=state.macros)
        elif isinstance(statement, nodes.Macro):
            bindings = {key: value for key, value in state.bindings.items() if key != statement.name}
            yield replace(state, bindings=bindings, macros={**state.macros, statement.name: _Macro(statement, state.bindings)})
        elif isinstance(statement, nodes.For):
            if statement.recursive or statement.test is not None:
                raise _IncompleteAnalysis("Recursive/filtered loops are not statically expanded")
            for iterable, original in self.expression(statement.iter, state):
                if not isinstance(iterable, nodes.Const) or not isinstance(iterable.value, (list, tuple, str, dict)):
                    raise _IncompleteAnalysis("A data-dependent loop has no finite static output")
                values = list(iterable.value)
                if len(values) > 16:
                    raise _IncompleteAnalysis("Jinja analysis reached its loop limit")
                if not values:
                    for result in self.body(statement.else_, [original]):
                        yield replace(result, bindings=state.bindings, macros=state.macros)
                    continue
                current = [original]
                for index, value in enumerate(values):
                    loop = nodes.Const({"index": index + 1, "index0": index, "first": index == 0,
                                        "last": index == len(values) - 1, "length": len(values),
                                        "revindex": len(values) - index, "revindex0": len(values) - index - 1})
                    member = nodes.Const(value)
                    member._analysis_dependencies = expression_dependencies(iterable)
                    loop._analysis_dependencies = expression_dependencies(iterable)
                    frames = [replace(item, macros=original.macros, bindings=self._bind({**original.bindings, "loop": loop},
                                                               statement.target, member)) for item in current]
                    current = self.body(statement.body, frames)
                for result in current:
                    yield replace(result, bindings=state.bindings, macros=state.macros)
        else:
            raise _IncompleteAnalysis(f"{type(statement).__name__} is not statically expanded")


def analyze_template(
    template: str | nodes.Template,
    *,
    environment: Environment,
    variables: Iterable[str] | None = None,
    aliases: Mapping[str, str] | None = None,
    known_values: Mapping[str, object] | None = None,
    assumptions: Iterable[tuple[nodes.Expr, bool]] = (),
    max_variants: int = 64,
    max_steps: int = 8192,
    namespace: str = "template",
) -> TemplateAnalysis:
    """Return guarded, normalized output expressions or an explicit unknown.

    ``aliases`` only describes domain-guaranteed equal input values. Local
    assignments are handled separately, with Jinja's assignment/scoping rules.
    Limits bound every intermediate expansion, not just the final result count.
    """
    try:
        tree = environment.parse(template) if isinstance(template, str) else deepcopy(template)
        for index, node in enumerate(tree.find_all(nodes.Filter)):
            if node.name in INTERNAL_FILTERS:
                raise _IncompleteAnalysis("An internal analysis filter cannot be used in source templates")
            if node.name in {"custom_index", "random"}:
                node._analysis_scope = namespace if node.name == "custom_index" else f"{namespace}:{index}"
        # Jinja's meta compiler can constant-fold filters. Discover loads without
        # compiling so even a caller-provided context filter is never invoked.
        macros = {node.name for node in tree.find_all(nodes.Macro)}
        inputs = set(variables) if variables is not None else {
            node.name for node in tree.find_all(nodes.Name)
            if node.ctx == "load" and node.name not in macros and node.name not in environment.globals
        }
        assumptions = tuple(assumptions)
        inputs.update(known_values or {})
        inputs.update(aliases or {})
        for expression, _ in assumptions:
            inputs.update(node.name for node in (expression, *expression.find_all(nodes.Name))
                          if isinstance(node, nodes.Name) and node.ctx == "load")
        bindings = {}
        for name in inputs:
            canonical = (aliases or {}).get(name, name)
            value = (nodes.Const(known_values[name]) if known_values is not None and name in known_values
                     else nodes.Name(INPUT_PREFIX + canonical, "load"))
            value._analysis_dependencies = frozenset({canonical})
            if isinstance(value, nodes.Name):
                value._analysis_input = True
            bindings[name] = value
        analyzer = _Analyzer(environment, max_variants, max_steps, namespace)
        states = [_State(bindings)]
        for assumption, truth in assumptions:
            states = analyzer._bounded(
                replace(result, conditions=condition)
                for state in states for expr, result in analyzer.expression(assumption, state)
                for condition in assume(result.conditions, expr, truth)
            )
        results = analyzer.body(tree.body, states)
        reasons = [part.reason for item in results for part in item.parts if isinstance(part, UnknownOutput)]
        return TemplateAnalysis(tuple(OutputVariant(item.parts, item.conditions) for item in results),
                                complete=not reasons, reason=reasons[0] if reasons else None)
    except (_IncompleteAnalysis, ExpressionAnalysisLimit, TemplateError, RecursionError) as exc:
        return TemplateAnalysis((), complete=False, reason=str(exc))
