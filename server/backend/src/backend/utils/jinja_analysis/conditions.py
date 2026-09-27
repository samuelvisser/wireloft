"""Bounded Boolean path conditions, not a general-purpose Jinja/SMT solver."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from jinja2 import nodes

from .expressions import expression_key


@dataclass(frozen=True)
class Condition:
    expression: nodes.Expr
    truth: bool


Conditions = tuple[Condition, ...]


def _comparison(condition: Condition):
    expression, truth = condition.expression, condition.truth
    if not isinstance(expression, nodes.Compare) or len(expression.ops) != 1:
        return None
    left, right, op = expression.expr, expression.ops[0].expr, expression.ops[0].op
    if isinstance(left, nodes.Const) and not isinstance(right, nodes.Const):
        if op in {"in", "notin"}:
            return None
        left, right = right, left
        op = {"lt": "gt", "lteq": "gteq", "gt": "lt", "gteq": "lteq"}.get(op, op)
    if not isinstance(right, nodes.Const):
        return None
    if not truth:
        op = {"eq": "ne", "ne": "eq", "in": "notin", "notin": "in",
              "lt": "gteq", "lteq": "gt", "gt": "lteq", "gteq": "lt"}.get(op)
    return expression_key(left), op, right.value


def _consistent(conditions: Conditions) -> bool:
    atoms: dict[tuple, bool] = {}
    equal: dict[tuple, object] = {}
    excluded: dict[tuple, list[object]] = {}
    members: dict[tuple, list[object]] = {}
    bounds: dict[tuple, list[tuple[str, object]]] = {}
    for condition in conditions:
        key = expression_key(condition.expression)
        if key in atoms and atoms[key] != condition.truth:
            return False
        atoms[key] = condition.truth
        comparison = _comparison(condition)
        if comparison is None:
            continue
        target, op, value = comparison
        if op == "eq":
            if target in equal and equal[target] != value:
                return False
            equal[target] = value
        elif op == "ne":
            excluded.setdefault(target, []).append(value)
        elif op in {"in", "notin"} and isinstance(value, (list, tuple)):
            if op == "in":
                members[target] = [item for item in members.get(target, value) if item in value]
                if not members[target]:
                    return False
            else:
                excluded.setdefault(target, []).extend(value)
        elif op in {"lt", "lteq", "gt", "gteq"} and type(value) in {int, float, str}:
            bounds.setdefault(target, []).append((op, value))

    def permitted(target, value):
        if value in excluded.get(target, []):
            return False
        if target in atoms and bool(value) != atoms[target]:
            return False
        for op, boundary in bounds.get(target, []):
            # Never invent Python coercions for a Jinja value of unknown type.
            if type(value) != type(boundary):
                continue
            if op == "lt" and not value < boundary or op == "lteq" and not value <= boundary:
                return False
            if op == "gt" and not value > boundary or op == "gteq" and not value >= boundary:
                return False
        return True

    for target, value in equal.items():
        if not permitted(target, value) or target in members and value not in members[target]:
            return False
    for target, values in members.items():
        if not any(permitted(target, value) for value in values):
            return False
    for limits in bounds.values():
        lower = [(value, op == "gt") for op, value in limits if op in {"gt", "gteq"}]
        upper = [(value, op == "lt") for op, value in limits if op in {"lt", "lteq"}]
        for lo, lo_open in lower:
            for hi, hi_open in upper:
                if type(lo) == type(hi) and (lo > hi or lo == hi and (lo_open or hi_open)):
                    return False
    return True


def assume(conditions: Conditions, expression: nodes.Expr, truth: bool) -> Iterable[Conditions]:
    """Split Boolean alternatives and discard contradictory atomic constraints.

    Unrecognized tests remain opaque predicates. Opposite uses of the same
    predicate can still be excluded without pretending to understand the test.
    """
    if isinstance(expression, nodes.Const):
        if bool(expression.value) == truth:
            yield conditions
        return
    if isinstance(expression, nodes.Not):
        yield from assume(conditions, expression.node, not truth)
        return
    if isinstance(expression, (nodes.And, nodes.Or)):
        conjunctive = isinstance(expression, nodes.And) == truth
        if conjunctive:
            for left in assume(conditions, expression.left, truth):
                yield from assume(left, expression.right, truth)
        else:
            yield from assume(conditions, expression.left, truth)
            for left in assume(conditions, expression.left, not truth):
                yield from assume(left, expression.right, truth)
        return
    if isinstance(expression, nodes.Compare) and len(expression.ops) > 1:
        terms = []
        left = expression.expr
        for operand in expression.ops:
            terms.append(nodes.Compare(left, [operand]))
            left = operand.expr
        combined = terms[0]
        for term in terms[1:]:
            combined = nodes.And(combined, term)
        yield from assume(conditions, combined, truth)
        return
    condition = Condition(expression, truth)
    key = expression_key(expression)
    if any(expression_key(item.expression) == key and item.truth == truth for item in conditions):
        yield conditions
        return
    combined = (*conditions, condition)
    if _consistent(combined):
        yield combined


def compatible(left: Conditions, right: Conditions) -> bool:
    return _consistent(left + right)


def equality_values(conditions: Conditions) -> dict[tuple, object]:
    result = {}
    for condition in conditions:
        comparison = _comparison(condition)
        if comparison is not None:
            key, op, value = comparison
            if op == "eq":
                result[key] = value
            elif op == "in" and isinstance(value, (list, tuple)) and len(value) == 1:
                result[key] = value[0]
    return result
