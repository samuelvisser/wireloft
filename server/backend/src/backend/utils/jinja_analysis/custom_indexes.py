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


def _target_names(target: nodes.Expr) -> frozenset[str]:
    if isinstance(target, (nodes.Name, nodes.NSRef)):
        return frozenset({target.name})
    if isinstance(target, nodes.Tuple):
        return frozenset(
            name
            for item in target.items
            for name in _target_names(item)
        )
    return frozenset()


def _loaded_names(node: nodes.Node) -> frozenset[str]:
    return frozenset(
        candidate.name
        for candidate in (node, *node.find_all(nodes.Name))
        if isinstance(candidate, nodes.Name) and candidate.ctx == "load"
    )


def _stored_names(node: nodes.Node) -> frozenset[str]:
    return frozenset(
        candidate.name
        for candidate in (node, *node.find_all(nodes.Name))
        if isinstance(candidate, nodes.Name) and candidate.ctx == "store"
    )


def _contains_requested_custom_index(node: nodes.Node, requested: frozenset[str]) -> bool:
    for filter_node in _custom_index_filters(node):
        source = filter_node.node
        if not isinstance(source, nodes.Const) or not isinstance(source.value, str):
            return True
        if source.value in requested:
            return True
    return False


def _reachability_names(tree: nodes.Template, requested: frozenset[str]) -> frozenset[str]:
    """Return local/input names that can affect whether a requested index executes.

    This is a conservative backwards slice. It deliberately follows assignments
    feeding relevant branch conditions, but excludes unrelated output/template
    calculations so unsupported Jinja elsewhere cannot poison index analysis.
    """
    needed: set[str] = set()
    changed = True
    while changed:
        changed = False

        for statement in tree.find_all(nodes.If):
            relevant = (
                _contains_requested_custom_index(statement, requested)
                or bool(_stored_names(statement) & needed)
            )
            if not relevant:
                continue
            tests = [statement.test, *(branch.test for branch in statement.elif_)]
            names = set().union(*(_loaded_names(test) for test in tests))
            if not names <= needed:
                needed.update(names)
                changed = True

        for statement in tree.find_all(nodes.For):
            relevant = (
                _contains_requested_custom_index(statement, requested)
                or bool(_stored_names(statement) & needed)
            )
            if not relevant:
                continue
            names = set(_loaded_names(statement.iter))
            if statement.test is not None:
                names.update(_loaded_names(statement.test))
            if not names <= needed:
                needed.update(names)
                changed = True

        for statement in tree.find_all(nodes.Assign):
            if not (_target_names(statement.target) & needed):
                continue
            names = set(_loaded_names(statement.node))
            if not names <= needed:
                needed.update(names)
                changed = True

        for statement in tree.find_all(nodes.AssignBlock):
            if not (_target_names(statement.target) & needed):
                continue
            names = set(_loaded_names(statement))
            if not names <= needed:
                needed.update(names)
                changed = True

        for statement in tree.find_all(nodes.With):
            for target, value in zip(statement.targets, statement.values, strict=True):
                if not (_target_names(target) & needed):
                    continue
                names = set(_loaded_names(value))
                if not names <= needed:
                    needed.update(names)
                    changed = True

        for statement in tree.find_all(nodes.Macro):
            if statement.name not in needed:
                continue
            parameter_names = {argument.name for argument in statement.args}
            local_names = _stored_names(statement)
            names = set(_loaded_names(statement)) - parameter_names - local_names
            if not names <= needed:
                needed.update(names)
                changed = True

    return frozenset(needed)


def _instrument_body(
    body: list[nodes.Stmt],
    requested: frozenset[str],
    reachability_names: frozenset[str],
) -> list[nodes.Stmt]:
    """Reduce a template to only statements affecting Custom Index reachability.

    Marker output makes a Custom Index call observable to the shared path
    analyzer. Ordinary rendered output and assignments unrelated to index
    reachability are removed entirely to help prevent false positives.
    """
    result: list[nodes.Stmt] = []
    for statement in body:
        if isinstance(statement, nodes.Macro):
            if _contains_requested_custom_index(statement, requested):
                raise _IncompleteAnalysis(
                    "Custom Index inside a macro cannot yet be proven statically"
                )
            if statement.name in reachability_names:
                result.append(statement)
            continue

        if isinstance(statement, nodes.If):
            if _custom_index_filters(statement.test):
                raise _IncompleteAnalysis(
                    "Custom Index values used as branch conditions cannot be proven statically"
                )
            statement.body = _instrument_body(
                statement.body, requested, reachability_names,
            )
            for branch in statement.elif_:
                if _custom_index_filters(branch.test):
                    raise _IncompleteAnalysis(
                        "Custom Index values used as branch conditions cannot be proven statically"
                    )
                branch.body = _instrument_body(
                    branch.body, requested, reachability_names,
                )
            statement.else_ = _instrument_body(
                statement.else_, requested, reachability_names,
            )
            if statement.body or any(branch.body for branch in statement.elif_) or statement.else_:
                result.append(statement)
            continue

        if isinstance(statement, nodes.For):
            if _custom_index_filters(statement.iter) or (
                statement.test is not None and _custom_index_filters(statement.test)
            ):
                raise _IncompleteAnalysis(
                    "Custom Index controlling a loop cannot be proven statically"
                )
            statement.body = _instrument_body(
                statement.body, requested, reachability_names,
            )
            statement.else_ = _instrument_body(
                statement.else_, requested, reachability_names,
            )
            if statement.body or statement.else_:
                result.append(statement)
            continue

        if isinstance(statement, nodes.With):
            keys: list[str] = []
            retained_targets: list[nodes.Expr] = []
            retained_values: list[nodes.Expr] = []
            for target, value in zip(statement.targets, statement.values, strict=True):
                for key in _keys_evaluated_by(value, requested):
                    if key not in keys:
                        keys.append(key)
                if _target_names(target) & reachability_names:
                    retained_targets.append(target)
                    retained_values.append(value)
            result.extend(_marker_statement(key, statement.lineno) for key in keys)
            statement.targets = retained_targets
            statement.values = retained_values
            statement.body = _instrument_body(
                statement.body, requested, reachability_names,
            )
            if statement.body:
                result.append(statement)
            continue

        if isinstance(statement, nodes.AssignBlock):
            if _contains_requested_custom_index(statement, requested):
                raise _IncompleteAnalysis(
                    "Custom Index inside an assignment block cannot yet be proven statically"
                )
            if _target_names(statement.target) & reachability_names:
                # The captured text is part of a later reachability condition,
                # so preserve it exactly rather than slicing ordinary output.
                result.append(statement)
            continue

        if isinstance(statement, nodes.Assign):
            keys = _keys_evaluated_by(statement, requested)
            result.extend(_marker_statement(key, statement.lineno) for key in keys)
            if _target_names(statement.target) & reachability_names:
                result.append(statement)
            continue

        if isinstance(statement, nodes.Output):
            keys = _keys_evaluated_by(statement, requested)
            result.extend(_marker_statement(key, statement.lineno) for key in keys)
            continue

        if _contains_requested_custom_index(statement, requested):
            raise _IncompleteAnalysis(
                f"Custom Index inside {type(statement).__name__} cannot be proven statically"
            )
        if _stored_names(statement) & reachability_names:
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
        reachability_names = _reachability_names(tree, requested)
        tree.body = _instrument_body(tree.body, requested, reachability_names)
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
    prev_template: str,
    new_template: str,
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

    prev = analyze_custom_index_usage(
        prev_template,
        environment=environment,
        keys=requested,
    )
    new = analyze_custom_index_usage(
        new_template,
        environment=environment,
        keys=requested,
    )
    if not prev.complete or not new.complete:
        return CustomIndexReachabilityComparison(
            CustomIndexReachabilityStatus.UNKNOWN,
            reason=prev.reason or new.reason,
        )

    dependencies = frozenset(
        dependency
        for key in requested
        for analysis in (prev, new)
        for dependency in analysis.usage_for(key).dependencies
    )
    for key in requested:
        if prev.usage_for(key).paths != new.usage_for(key).paths:
            return CustomIndexReachabilityComparison(
                CustomIndexReachabilityStatus.CHANGED,
                dependencies=dependencies,
                reason=f"Custom Index '{key}' has different assignment conditions",
            )
    return CustomIndexReachabilityComparison(
        CustomIndexReachabilityStatus.UNCHANGED,
        dependencies=dependencies,
    )
