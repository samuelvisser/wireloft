"""Scoped expression normalization. Jinja, not WireLoft, evaluates constants."""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy

from jinja2 import Environment, nodes
from jinja2.runtime import EvalContext
from jinja2.visitor import NodeTransformer


# Context-dependent calls must stay symbolic, including literal custom-index keys.
VOLATILE_FILTERS = frozenset({"random", "custom_index"})
EMIT_FILTER = "__wireloft_analysis_emit"


class ExpressionAnalysisLimit(Exception):
    pass


def _check_size(node: nodes.Node, limit: int = 2048) -> None:
    pending = [node]
    while pending:
        limit -= 1
        if limit < 0:
            raise ExpressionAnalysisLimit("Jinja analysis reached its expression-size limit")
        current = pending.pop()
        if isinstance(current, nodes.Const) and isinstance(current.value, str) and len(current.value) > 8192:
            raise ExpressionAnalysisLimit("Jinja analysis reached its constant-size limit")
        pending.extend(current.iter_child_nodes())


def expression_key(value: object) -> tuple:
    """A structural key without source locations, object reprs or environments."""
    if isinstance(value, nodes.Node):
        return (type(value).__name__, getattr(value, "_analysis_scope", None),
                *(expression_key(getattr(value, field)) for field in value.fields))
    if isinstance(value, (list, tuple)):
        return (type(value).__name__, *(expression_key(item) for item in value))
    if isinstance(value, dict):
        return ("dict", *(sorted((expression_key(k), expression_key(v)) for k, v in value.items())))
    return (type(value).__name__, value)


def expression_dependencies(node: nodes.Node) -> frozenset[str]:
    """Original input dependencies survive alias substitution/constant folding."""
    dependencies = set(getattr(node, "_analysis_dependencies", ()))
    if isinstance(node, nodes.Name):
        dependencies.add(node.name.removeprefix("__wireloft_input_"))
    if isinstance(node, nodes.Filter) and node.name in VOLATILE_FILTERS:
        dependencies.add("@" + node.name)
    if isinstance(node, nodes.Call):
        dependencies.add("@call")
    for child in node.iter_child_nodes():
        dependencies.update(expression_dependencies(child))
    return frozenset(dependencies)


def analysis_environment(environment: Environment) -> Environment:
    result = environment.overlay()
    result.filters = dict(environment.filters)
    result.filters[EMIT_FILTER] = environment.finalize or str
    return result


def depends_on_runtime(node: nodes.Node) -> bool:
    if isinstance(node, (nodes.Call, nodes.Name)):
        return True
    if isinstance(node, nodes.Filter) and node.name in VOLATILE_FILTERS:
        return True
    return any(depends_on_runtime(child) for child in node.iter_child_nodes())


class NormalizeExpression(NodeTransformer):
    def __init__(self, environment: Environment, bindings: Mapping[str, nodes.Expr]):
        self.environment = environment
        self.bindings = bindings

    def visit_Name(self, node: nodes.Name, *args, **kwargs):
        # A binding was normalized when assigned. Revisiting it here would make
        # later assignments retroactively change earlier aliases.
        if node.ctx == "load" and not getattr(node, "_analysis_input", False) and node.name in self.bindings:
            _check_size(self.bindings[node.name])
            return deepcopy(self.bindings[node.name])
        return node

    def generic_visit(self, node: nodes.Node, *args, **kwargs):
        node = super().generic_visit(node, *args, **kwargs)
        if isinstance(node, nodes.Expr) and not isinstance(node, (nodes.Const, nodes.TemplateData)):
            if not depends_on_runtime(node):
                if isinstance(node, nodes.Pow):
                    raise ExpressionAnalysisLimit("Exponentiation is not constant-folded during analysis")
                if isinstance(node, nodes.Mul) and isinstance(node.left, nodes.Const) and isinstance(node.right, nodes.Const):
                    left, right = node.left.value, node.right.value
                    if isinstance(left, int) and isinstance(right, (str, list, tuple)):
                        left, right = right, left
                    if isinstance(left, (str, list, tuple)) and isinstance(right, int) and len(left) * max(0, right) > 8192:
                        raise ExpressionAnalysisLimit("Jinja analysis reached its constant-size limit")
                try:
                    value = node.as_const(EvalContext(self.environment))
                    constant = nodes.Const.from_untrusted(value).set_lineno(node.lineno)
                    constant._analysis_dependencies = expression_dependencies(node)
                    return constant
                except (nodes.Impossible, ArithmeticError, TypeError, ValueError):
                    pass
        return node


def normalize_expression(
    node: nodes.Expr, bindings: Mapping[str, nodes.Expr], environment: Environment,
) -> nodes.Expr:
    _check_size(node)
    result = NormalizeExpression(environment, bindings).visit(deepcopy(node))
    _check_size(result)
    return result


def emitted_expression(node: nodes.Expr) -> nodes.Expr:
    """Represent finalization inside a captured block/macro without executing it."""
    return nodes.Filter(node, EMIT_FILTER, [], [], None, None)
