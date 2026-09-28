"""Static reachability analysis for Custom Index calls in output templates."""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum
from typing import Iterable

from jinja2 import Environment, TemplateError, nodes

from .expressions import expression_dependencies, expression_key
from .paths import analyze_template


ConditionSignature = frozenset[tuple[tuple, bool]]
_MARKER_PREFIX = "\x00WIRELOFT_CUSTOM_INDEX:"
_MARKER_SUFFIX = "\x00"


class CustomIndexReachabilityStatus(StrEnum):
    UNCHANGED = "unchanged"
    CHANGED = "changed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class CustomIndexUsage:
    key: str
    paths: frozenset[ConditionSignature]
    dependencies: frozenset[str]


@dataclass(frozen=True)
class CustomIndexUsageAnalysis:
    usages: tuple[CustomIndexUsage, ...]
    complete: bool = True
    reason: str | None = None

    def usage_for(self, key: str) -> CustomIndexUsage:
        return next(
            (usage for usage in self.usages if usage.key == key),
            CustomIndexUsage(key, frozenset(), frozenset()),
        )


@dataclass(frozen=True)
class CustomIndexReachabilityComparison:
    status: CustomIndexReachabilityStatus
    dependencies: frozenset[str] = frozenset()
    reason: str | None = None


class _IncompleteAnalysis(Exception):
    pass


def _custom_index_filters(node: nodes.Node) -> tuple[nodes.Filter, ...]:
    return tuple(
        candidate
        for candidate in (node, *node.find_all(nodes.Filter))
        if isinstance(candidate, nodes.Filter) and candidate.name == "custom_index"
    )


def _has_conditional_evaluation(node: nodes.Node) -> bool:
    return any(
        _custom_index_filters(candidate)
        for candidate in (node, *node.find_all((nodes.And, nodes.Or, nodes.CondExpr)))
        if isinstance(candidate, (nodes.And, nodes.Or, nodes.CondExpr))
    )


def _marker(key: str) -> str:
    return f"{_MARKER_PREFIX}{key}{_MARKER_SUFFIX}"


def _marker_statement(key: str, lineno: int) -> nodes.Output:
    return nodes.Output([nodes.TemplateData(_marker(key))]).set_lineno(lineno)


def _keys_evaluated_by(node: nodes.Node, requested: frozenset[str]) -> tuple[str, ...]:
    filters = _custom_index_filters(node)
    if not filters:
        return ()
    if _has_conditional_evaluation(node):
        raise _IncompleteAnalysis(
            "Custom Index inside a short-circuit expression cannot be proven statically"
        )

    keys: list[str] = []
    for filter_node in filters:
        source = filter_node.node
        if not isinstance(source, nodes.Const) or not isinstance(source.value, str):
            raise _IncompleteAnalysis("Custom Index key is not a literal string")
        if source.value in requested and source.value not in keys:
            keys.append(source.value)
    return tuple(keys)


def _instrument_body(body: list[nodes.Stmt], requested: frozenset[str]) -> list[nodes.Stmt]:
    """Insert marker output where a Custom Index filter is definitely evaluated.

    Control-flow expansion remains the responsibility of the existing Jinja
    analyzer. This pass only exposes Custom Index evaluation as observable
    output, allowing the shared analyzer to derive the guarded execution paths.
    """
    result: list[nodes.Stmt] = []
    for statement in body:
        if isinstance(statement, nodes.Macro):
            if _custom_index_filters(statement):
                raise _IncompleteAnalysis(
                    "Custom Index inside a macro cannot yet be proven statically"
                )
            result.append(statement)
            continue

        if isinstance(statement, nodes.If):
            if _custom_index_filters(statement.test):
                raise _IncompleteAnalysis(
                    "Custom Index values used as branch conditions cannot be proven statically"
                )
            statement.body = _instrument_body(statement.body, requested)
            for branch in statement.elif_:
                if _custom_index_filters(branch.test):
                    raise _IncompleteAnalysis(
                        "Custom Index values used as branch conditions cannot be proven statically"
                    )
                branch.body = _instrument_body(branch.body, requested)
            statement.else_ = _instrument_body(statement.else_, requested)
            result.append(statement)
            continue

        if isinstance(statement, nodes.For):
            if _custom_index_filters(statement.iter) or (
                statement.test is not None and _custom_index_filters(statement.test)
            ):
                raise _IncompleteAnalysis(
                    "Custom Index controlling a loop cannot be proven statically"
                )
            statement.body = _instrument_body(statement.body, requested)
            statement.else_ = _instrument_body(statement.else_, requested)
            result.append(statement)
            continue

        if isinstance(statement, nodes.With):
            keys: list[str] = []
            for value in statement.values:
                for key in _keys_evaluated_by(value, requested):
                    if key not in keys:
                        keys.append(key)
            result.extend(_marker_statement(key, statement.lineno) for key in keys)
            statement.body = _instrument_body(statement.body, requested)
            result.append(statement)
            continue

        if isinstance(statement, nodes.AssignBlock):
            if statement.filter is not None and _custom_index_filters(statement.filter):
                raise _IncompleteAnalysis(
                    "Custom Index as an assignment-block filter cannot be proven statically"
                )
            statement.body = _instrument_body(statement.body, requested)
            result.append(statement)
            continue

        if isinstance(statement, (nodes.Assign, nodes.Output)):
            keys = _keys_evaluated_by(statement, requested)
            result.extend(_marker_statement(key, statement.lineno) for key in keys)
            result.append(statement)
            continue

        if _custom_index_filters(statement):
            raise _IncompleteAnalysis(
                f"Custom Index inside {type(statement).__name__} cannot be proven statically"
            )
        result.append(statement)
    return result


def _condition_signature(variant) -> ConditionSignature:
    return frozenset(
        (expression_key(condition.expression), condition.truth)
        for condition in variant.conditions
    )


def analyze_custom_index_usage(
    template: str,
    *,
    environment: Environment,
    keys: Iterable[str],
) -> CustomIndexUsageAnalysis:
    """Return guarded execution paths for requested Custom Index keys.

    The shared path-sensitive Jinja analyzer performs all branch, assignment,
    scope and bounded-loop reasoning. This adapter merely makes index-filter
    evaluation visible to it.
    """
    requested = frozenset(keys)
    if not requested:
        return CustomIndexUsageAnalysis(())

    try:
        if any(_marker(key) in template for key in requested):
            raise _IncompleteAnalysis("Template contains an internal Custom Index analysis marker")
        tree = environment.parse(template)
        tree = deepcopy(tree)
        tree.body = _instrument_body(tree.body, requested)
        analysis = analyze_template(
            tree,
            environment=environment,
            namespace="custom-index-reachability",
        )
        if not analysis.complete:
            return CustomIndexUsageAnalysis(
                (),
                complete=False,
                reason=analysis.reason,
            )

        paths: dict[str, set[ConditionSignature]] = {key: set() for key in requested}
        dependencies: dict[str, set[str]] = {key: set() for key in requested}
        for variant in analysis.variants:
            emitted = "".join(part for part in variant.parts if isinstance(part, str))
            variant_dependencies = frozenset(
                dependency
                for condition in variant.conditions
                for dependency in expression_dependencies(condition.expression)
            )
            if "@custom_index" in variant_dependencies:
                return CustomIndexUsageAnalysis(
                    (),
                    complete=False,
                    reason="A Custom Index value affects another Custom Index assignment condition",
                )
            for key in requested:
                if _marker(key) not in emitted:
                    continue
                paths[key].add(_condition_signature(variant))
                dependencies[key].update(variant_dependencies)

        return CustomIndexUsageAnalysis(tuple(
            CustomIndexUsage(
                key=key,
                paths=frozenset(paths[key]),
                dependencies=frozenset(dependencies[key]),
            )
            for key in sorted(requested)
        ))
    except (
        _IncompleteAnalysis,
        TemplateError,
        RecursionError,
        TypeError,
        ValueError,
    ) as exc:
        return CustomIndexUsageAnalysis((), complete=False, reason=str(exc))


def compare_custom_index_reachability(
    saved_template: str,
    draft_template: str,
    *,
    environment: Environment,
    keys: Iterable[str],
) -> CustomIndexReachabilityComparison:
    """Prove whether requested indexes are assigned to the same episode set.

    Only UNCHANGED is safe for persisted assignment reuse. A changed or
    unprovable program deliberately falls back to historical simulation.
    """
    requested = frozenset(keys)
    if not requested:
        return CustomIndexReachabilityComparison(CustomIndexReachabilityStatus.UNCHANGED)

    saved = analyze_custom_index_usage(
        saved_template,
        environment=environment,
        keys=requested,
    )
    draft = analyze_custom_index_usage(
        draft_template,
        environment=environment,
        keys=requested,
    )
    if not saved.complete or not draft.complete:
        return CustomIndexReachabilityComparison(
            CustomIndexReachabilityStatus.UNKNOWN,
            reason=saved.reason or draft.reason,
        )

    dependencies = frozenset(
        dependency
        for key in requested
        for analysis in (saved, draft)
        for dependency in analysis.usage_for(key).dependencies
    )
    for key in requested:
        if saved.usage_for(key).paths != draft.usage_for(key).paths:
            return CustomIndexReachabilityComparison(
                CustomIndexReachabilityStatus.CHANGED,
                dependencies=dependencies,
                reason=f"Custom Index '{key}' has different assignment conditions",
            )
    return CustomIndexReachabilityComparison(
        CustomIndexReachabilityStatus.UNCHANGED,
        dependencies=dependencies,
    )
