"""Compare guarded symbolic output layouts without rendering example media."""
from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from copy import deepcopy
from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePosixPath
import re

from jinja2 import Environment, nodes
from jinja2.visitor import NodeTransformer

from .conditions import Conditions, compatible, equality_values
from .expressions import (
    EMIT_FILTER, ExpressionAnalysisLimit, analysis_environment, depends_on_runtime, expression_dependencies,
    expression_key, normalize_expression,
)
from .paths import OutputVariant, TemplateAnalysis, UnknownOutput


class OutputOverlap(StrEnum):
    OVERLAP = "overlap"
    DISJOINT = "disjoint"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class OutputComparison:
    status: OutputOverlap
    reason: str | None = None


class _MarkerCollision(Exception):
    pass


@dataclass(frozen=True)
class _Symbol:
    key: tuple


class _SubstituteEqualities(NodeTransformer):
    def __init__(self, conditions: Conditions):
        self.values = equality_values(conditions)

    def visit(self, node, *args, **kwargs):
        key = expression_key(node)
        if key in self.values:
            return nodes.Const(self.values[key])
        return super().visit(node, *args, **kwargs)


def _fragments(expression: nodes.Expr, environment: Environment, *, concatenated: bool = False):
    # WireLoft's emitted-value finalizer is character-wise and idempotent. Thus
    # string concatenation and repeated finalization can be normalized without
    # injecting marker values into filters or changing Jinja filter semantics.
    if isinstance(expression, nodes.Concat):
        for child in expression.nodes:
            yield from _fragments(child, environment, concatenated=True)
    elif isinstance(expression, nodes.Filter) and expression.name == EMIT_FILTER:
        yield from _fragments(expression.node, environment)
    elif isinstance(expression, nodes.Const):
        value = str(expression.value) if concatenated else expression.value
        yield str(environment.finalize(value) if environment.finalize else value)
    else:
        yield _Symbol(expression_key(expression))


def _pattern(
    variant: OutputVariant,
    conditions: Conditions,
    environment: Environment,
    finalize_path: Callable[[str], str],
    symbols: dict[tuple, str],
    prefix: str,
):
    for condition in conditions:
        constrained = _SubstituteEqualities(conditions).visit(deepcopy(condition.expression))
        constrained = normalize_expression(constrained, {}, environment)
        if isinstance(constrained, nodes.Const) and bool(constrained.value) != condition.truth:
            return False
    fragments = []
    for part in variant.parts:
        if isinstance(part, UnknownOutput):
            return None
        if isinstance(part, str):
            fragments.append(part)
            continue
        part = _SubstituteEqualities(conditions).visit(deepcopy(part))
        part = normalize_expression(part, {}, environment)
        if expression_dependencies(part) & {"@random", "@call"}:
            return None
        if not isinstance(part, nodes.Const) and not depends_on_runtime(part):
            # A constant expression that Jinja cannot evaluate (e.g. division
            # by zero) is not evidence of a possible rendered filename.
            return None
        fragments.extend(_fragments(part, environment))
    text = ""
    expected = Counter()
    for part in fragments:
        if isinstance(part, str):
            text += part
        else:
            marker = symbols.setdefault(part.key, f"{prefix}{len(symbols)}END")
            text += marker
            expected[marker] += 1
    # Symbols cannot introduce path separators: the real output finalizer strips
    # those before the whole-path filename restriction policy is applied.
    text = str(PurePosixPath(finalize_path(text)))
    reverse = {marker: _Symbol(key) for key, marker in symbols.items()}
    actual = Counter(re.findall(f"{re.escape(prefix)}[0-9]+END", text))
    if any(count > expected[marker] for marker, count in actual.items()):
        raise _MarkerCollision
    if actual != expected:
        return None
    tokens = []
    for part in re.split(f"({re.escape(prefix)}[0-9]+END)", text):
        if part in reverse:
            tokens.append(reverse[part])
        else:
            tokens.extend(part)
    return tokens


def _disjoint(left: list, right: list) -> bool:
    """Only prove separation from fixed output before/after dynamic values.

    Cancelling equal symbols would seem attractive, but filename policies can
    change component boundaries (empty values) or add a Windows reserved-name
    prefix. Never claim disjointness using a placeholder's particular length.
    """
    if not any(isinstance(item, _Symbol) for item in (*left, *right)):
        return left != right
    for pairs in (zip(left, right), zip(reversed(left), reversed(right))):
        for a, b in pairs:
            if isinstance(a, _Symbol) or isinstance(b, _Symbol):
                break
            if a != b:
                return True
    return False


def compare_outputs(
    left: TemplateAnalysis,
    right: TemplateAnalysis,
    *,
    environment: Environment,
    finalize_left: Callable[[str], str] = str,
    finalize_right: Callable[[str], str] = str,
) -> OutputComparison:
    """Compare layouts for the same semantic input (not arbitrary other media).

    OVERLAP means equivalent symbolic output on compatible branch conditions.
    UNKNOWN is deliberately distinct from a proof of disjoint output. Arbitrary
    relationships between different filters/expressions are not solved here.
    """
    evaluator = analysis_environment(environment)
    uncertain = not left.complete or not right.complete
    for lhs in left.variants:
        for rhs in right.variants:
            if not compatible(lhs.conditions, rhs.conditions):
                continue
            conditions = lhs.conditions + rhs.conditions
            symbols: dict[tuple, str] = {}
            # Never confuse a user's literal filename text with a symbolic token.
            literals = "".join(part for variant in (lhs, rhs) for part in variant.parts if isinstance(part, str))
            prefix = "WLJINJASYMBOL"
            while prefix in literals:
                prefix += "X"
            while True:
                try:
                    lparts = _pattern(lhs, conditions, evaluator, finalize_left, symbols, prefix)
                    rparts = _pattern(rhs, conditions, evaluator, finalize_right, symbols, prefix)
                    break
                except _MarkerCollision:
                    prefix += "X"
                    symbols.clear()
                except ExpressionAnalysisLimit as exc:
                    return OutputComparison(OutputOverlap.UNKNOWN, str(exc))
            if lparts is False or rparts is False:
                continue
            if lparts is None or rparts is None:
                uncertain = True
            elif lparts == rparts:
                return OutputComparison(OutputOverlap.OVERLAP, "Equivalent output on compatible Jinja branches")
            elif not _disjoint(lparts, rparts):
                uncertain = True
    if uncertain:
        return OutputComparison(OutputOverlap.UNKNOWN, left.reason or right.reason or "Output expressions could not be proven equal or disjoint")
    return OutputComparison(OutputOverlap.DISJOINT)
