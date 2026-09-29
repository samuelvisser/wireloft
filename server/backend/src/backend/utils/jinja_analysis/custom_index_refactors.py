"""Bounded, source-preserving Jinja refactors for the editor's index advisory.

These are optional source edits, never a rendering transform. Only move a
single-use, closed, total expression into an existing guarded use. Reparse every
edit and compare its AST with the intended edit, including all untouched code.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
import math
import re

from jinja2 import Environment, TemplateError, nodes
from jinja2.visitor import NodeTransformer

from .expressions import expression_key


@dataclass(frozen=True)
class CustomIndexSuggestion:
    before: str
    after: str
    output_template: str


class _Unsafe(Exception):
    pass


def _index(node: nodes.Node, key: str) -> bool:
    return (
        isinstance(node, nodes.Filter) and node.name == "custom_index"
        and isinstance(node.node, nodes.Const) and node.node.value == key
        and not (node.args or node.kwargs or node.dyn_args or node.dyn_kwargs)
    )


def _all(node: nodes.Node, cls):
    return ([node] if isinstance(node, cls) else []) + list(node.find_all(cls))


def _loads(node: nodes.Node, name: str) -> list[nodes.Name]:
    return [item for item in _all(node, nodes.Name) if item.ctx == "load" and item.name == name]


def _source(node: nodes.Node) -> str:
    """Serialize edited expressions, not blocks; a reparse verifies precedence."""
    if isinstance(node, nodes.Const):
        if node.value is None:
            return "none"
        if isinstance(node.value, bool):
            return "true" if node.value else "false"
        if isinstance(node.value, (str, int, float)):
            if isinstance(node.value, float) and not math.isfinite(node.value):
                raise _Unsafe()
            return repr(node.value)
    if isinstance(node, nodes.Name):
        return node.name
    if isinstance(node, nodes.Concat):
        return "(" + " ~ ".join(_source(item) for item in node.nodes) + ")"
    binary = {nodes.Add: "+", nodes.Sub: "-", nodes.Mul: "*", nodes.Div: "/", nodes.FloorDiv: "//",
              nodes.Mod: "%", nodes.Pow: "**", nodes.And: "and", nodes.Or: "or"}
    if type(node) in binary:
        return f"({_source(node.left)} {binary[type(node)]} {_source(node.right)})"
    unary = {nodes.Not: "not ", nodes.Neg: "-", nodes.Pos: "+"}
    if type(node) in unary:
        return f"({unary[type(node)]}{_source(node.node)})"
    if isinstance(node, nodes.Compare):
        operators = {"eq": "==", "ne": "!=", "lt": "<", "lteq": "<=", "gt": ">", "gteq": ">=", "in": "in", "notin": "not in"}
        return "(" + _source(node.expr) + "".join(
            f" {operators[item.op]} {_source(item.expr)}" for item in node.ops
        ) + ")"
    if isinstance(node, nodes.CondExpr):
        otherwise = "" if node.expr2 is None else " else " + _source(node.expr2)
        return f"({_source(node.expr1)} if {_source(node.test)}{otherwise})"
    if isinstance(node, nodes.Getattr):
        return f"({_source(node.node)}).{node.attr}"
    if isinstance(node, nodes.Getitem):
        return f"({_source(node.node)})[{_source(node.arg)}]"
    if isinstance(node, (nodes.List, nodes.Tuple)):
        inner = ", ".join(_source(item) for item in node.items)
        return "[" + inner + "]" if isinstance(node, nodes.List) else "(" + inner + ",)"
    if isinstance(node, nodes.Dict):
        return "{" + ", ".join(f"{_source(item.key)}: {_source(item.value)}" for item in node.items) + "}"
    if isinstance(node, (nodes.Call, nodes.Filter, nodes.Test)):
        if node.dyn_args is not None or node.dyn_kwargs is not None:
            raise _Unsafe()
        args = [_source(item) for item in node.args]
        args.extend(f"{item.key}={_source(item.value)}" for item in node.kwargs)
        tail = "(" + ", ".join(args) + ")"
        if isinstance(node, nodes.Call):
            return f"{_source(node.node)}{tail}"
        operator = " | " if isinstance(node, nodes.Filter) else " is "
        return "(" + _source(node.node) + operator + node.name + (tail if args else "") + ")"
    raise _Unsafe()


def _movable(node: nodes.Node, key: str) -> str | None:
    """Known-total closed computations only; never execute a user's filter.

    No free variables means no closure/rebinding/evaluation-timing assumptions.
    Numeric format strings have a deliberately small, total whitelist.
    """
    if _index(node, key):
        return "int"
    if isinstance(node, nodes.Const):
        return "str" if isinstance(node.value, str) else "int" if type(node.value) is int else None
    if isinstance(node, nodes.Concat) and all(_movable(item, key) for item in node.nodes):
        return "str"
    if isinstance(node, nodes.Filter) and not (node.kwargs or node.dyn_args or node.dyn_kwargs):
        value_type = _movable(node.node, key)
        if not node.args:
            if node.name == "string" and value_type:
                return "str"
            if node.name in {"upper", "lower", "capitalize", "title", "trim"} and value_type == "str":
                return "str"
            if node.name in {"int", "abs"} and value_type == "int":
                return "int"
        if node.name == "format" and isinstance(node.node, nodes.Const) and isinstance(node.node.value, str):
            # Literals and %% plus exactly one bounded integer/string conversion.
            pattern = node.node.value
            conversions = re.findall(r"%(?:0?[1-9][0-9]?)?[ds]", pattern.replace("%%", ""))
            rest = re.sub(r"%(?:0?[1-9][0-9]?)?[ds]", "", pattern.replace("%%", ""))
            if len(conversions) == len(node.args) == 1 and "%" not in rest:
                kind = _movable(node.args[0], key)
                if kind and (conversions[0].endswith("s") or kind == "int"):
                    return "str"
    return None


class _Replace(NodeTransformer):
    def __init__(self, changes: dict[int, nodes.Node | None]):
        self.changes = changes

    def visit(self, node, *args, **kwargs):
        if id(node) in self.changes:
            return deepcopy(self.changes[id(node)])
        return super().visit(node, *args, **kwargs)


def _replaced(tree: nodes.Node, changes: dict[int, nodes.Node | None]) -> nodes.Node:
    memo: dict = {}
    cloned = deepcopy(tree, memo)
    replacements = {id(memo[old]): new for old, new in changes.items() if old in memo}
    return _Replace(replacements).visit(cloned)


def _shape(tree: nodes.Node):
    """Removing a set can make Jinja merge adjacent output/text nodes."""
    class Merge(NodeTransformer):
        def generic_visit(self, node, *args, **kwargs):
            node = super().generic_visit(node, *args, **kwargs)
            for field in node.fields:
                values = getattr(node, field)
                if not isinstance(values, list):
                    continue
                merged = []
                for value in values:
                    if merged and isinstance(value, nodes.Output) and isinstance(merged[-1], nodes.Output):
                        merged[-1].nodes.extend(value.nodes)
                    else:
                        merged.append(value)
                if isinstance(node, nodes.Output):
                    joined = []
                    for value in merged:
                        if joined and isinstance(value, nodes.TemplateData) and isinstance(joined[-1], nodes.TemplateData):
                            joined[-1].data += value.data
                        elif not isinstance(value, nodes.TemplateData) or value.data:
                            joined.append(value)
                    merged = joined
                setattr(node, field, merged)
            if isinstance(node, nodes.Output):
                # A neighboring Output may have just been joined by its parent.
                return node
            for child in node.iter_child_nodes():
                if isinstance(child, nodes.Output):
                    joined = []
                    for value in child.nodes:
                        if joined and isinstance(value, nodes.TemplateData) and isinstance(joined[-1], nodes.TemplateData):
                            joined[-1].data += value.data
                        else:
                            joined.append(value)
                    child.nodes = joined
            return node
    return expression_key(Merge().visit(deepcopy(tree)))


@dataclass(frozen=True)
class _Tag:
    start: int
    end: int
    kind: str
    header: nodes.Node


class _Edits:
    """Locate only complete Jinja tags; untouched code/comments stay byte exact."""
    def __init__(self, source: str, tree: nodes.Template, environment: Environment):
        self.source, self.tree, self.environment = source, tree, environment
        self.edits: list[tuple[int, int, str]] = []
        self.tags: list[_Tag] = []
        self.blocks: list[tuple[int, int]] = []
        stack: list[tuple[str, int]] = []
        tokens = list(environment.lex(source))
        if "".join(value for _, _, value in tokens) != source:
            raise _Unsafe()
        start = None
        offset = 0
        for _, kind, value in tokens:
            if kind in {"variable_begin", "block_begin"}:
                start = offset
            offset += len(value)
            if kind not in {"variable_end", "block_end"} or start is None:
                continue
            text = source[start:offset]
            keyword = "output" if kind == "variable_end" else next(
                (value for _, token, value in environment.lex(text) if token == "name"), "",
            )
            opener = keyword in {"if", "for", "macro", "with", "filter", "call", "block", "autoescape"}
            if keyword == "set":
                try:
                    opener = isinstance(environment.parse(text + "{% endset %}").body[0], nodes.AssignBlock)
                except TemplateError:
                    pass
            if opener:
                stack.append((keyword, start))
            elif keyword.startswith("end") and stack and stack[-1][0] == keyword[3:]:
                _, block_start = stack.pop()
                self.blocks.append((block_start, offset))
            try:
                parse_text = text
                if keyword == "elif":
                    parse_text = text.replace("elif", "if", 1) + "{% endif %}"
                elif keyword in {"if", "macro"}:
                    parse_text += "{% end" + keyword + " %}"
                header = environment.parse(parse_text).body[0]
                if keyword in {"output", "set", "if", "elif", "macro"}:
                    self.tags.append(_Tag(start, offset, keyword, header))
            except (TemplateError, IndexError):
                pass
            start = None

    def _tag(self, test) -> _Tag:
        matches = [tag for tag in self.tags if test(tag)]
        if len(matches) != 1:
            raise _Unsafe()
        return matches[0]

    def remove(self, assignment: nodes.Assign):
        tag = self._tag(lambda tag: tag.kind == "set" and expression_key(tag.header) == expression_key(assignment))
        self.edits.append((tag.start, tag.end, ""))

    def expressions(self, changes: dict[int, nodes.Node | None]):
        """Rewrite the smallest owning output/assignment/condition tag."""
        for parent in _all(self.tree, (nodes.Output, nodes.Assign, nodes.If)):
            roots = parent.nodes if isinstance(parent, nodes.Output) else [parent.node if isinstance(parent, nodes.Assign) else parent.test]
            for root in roots:
                if isinstance(root, nodes.TemplateData):
                    continue
                changed = _replaced(root, changes)
                if expression_key(root) == expression_key(changed):
                    continue
                if isinstance(parent, nodes.Output):
                    tag = self._tag(lambda t: t.kind == "output" and len(t.header.nodes) == 1 and expression_key(t.header.nodes[0]) == expression_key(root))
                    expression = _source(changed)
                    if isinstance(changed, nodes.Filter):
                        expression = expression[1:-1]
                    text = "{{ " + expression + " }}"
                elif isinstance(parent, nodes.Assign):
                    tag = self._tag(lambda t: t.kind == "set" and expression_key(t.header) == expression_key(parent))
                    text = "{% set " + _source(parent.target) + " = " + _source(changed) + " %}"
                else:
                    tag = self._tag(lambda t: t.kind in {"if", "elif"} and expression_key(t.header.test) == expression_key(root))
                    text = "{% " + tag.kind + " " + _source(changed) + " %}"
                self.edits.append((tag.start, tag.end, text))

    def macro(self, original: nodes.Macro, revised: nodes.Macro):
        tag = self._tag(lambda t: t.kind == "macro" and t.header.name == original.name)
        defaults = len(revised.args) - len(revised.defaults)
        args = [arg.name + ("=" + _source(revised.defaults[i - defaults]) if i >= defaults else "") for i, arg in enumerate(revised.args)]
        self.edits.append((tag.start, tag.end, "{% macro " + revised.name + "(" + ", ".join(args) + ") %}"))

    def finish(self, expected: nodes.Template) -> CustomIndexSuggestion:
        edits = sorted(set(self.edits))
        if not edits or any(a[1] > b[0] for a, b in zip(edits, edits[1:])):
            raise _Unsafe()
        revised = self.source
        for start, end, text in reversed(edits):
            revised = revised[:start] + text + revised[end:]
        if len(revised) > 4096 or _shape(self.environment.parse(revised)) != _shape(expected):
            raise _Unsafe()
        # Include enclosing native blocks in the review, rather than showing a
        # detached {{ value }} without the condition that makes the edit useful.
        ranges = set()
        for start, end, _ in edits:
            enclosing = [(a, b) for a, b in self.blocks if a <= start and end <= b]
            ranges.add(min(enclosing, key=lambda span: span[0]) if enclosing else (start, end))
        ranges = sorted(span for span in ranges if not any(other != span and other[0] <= span[0] and span[1] <= other[1] for other in ranges))
        after = []
        for start, end in ranges:
            fragment = self.source[start:end]
            for a, b, text in reversed(edits):
                if start <= a < b <= end:
                    fragment = fragment[:a - start] + text + fragment[b - start:]
            if fragment:
                after.append(fragment)
        return CustomIndexSuggestion(
            before="\n".join(self.source[start:end] for start, end in ranges),
            after="\n".join(after),
            output_template=revised,
        )


class _Context:
    def __init__(self, tree: nodes.Template):
        self.tree = tree
        self.parents = {}
        self.writes = Counter(n.name for n in tree.find_all(nodes.Name) if n.ctx in {"store", "param"})
        self.bindings = {n.target.name: n.node for n in tree.body if isinstance(n, nodes.Assign) and isinstance(n.target, nodes.Name)}
        counts = Counter(n.name for n in tree.find_all(nodes.Macro))
        self.macros = {n.name: n for n in tree.body if isinstance(n, nodes.Macro) and counts[n.name] == 1}
        def visit(node):
            if len(self.parents) > 2048:
                raise _Unsafe()
            for field in node.fields:
                value = getattr(node, field)
                children = enumerate(value) if isinstance(value, list) else [(None, value)]
                for index, child in children:
                    if isinstance(child, nodes.Node):
                        self.parents[id(child)] = (node, field, index)
                        visit(child)
        visit(tree)

    def invocation(self, macro: nodes.Macro) -> tuple[nodes.Call, dict[str, nodes.Expr]]:
        if self.macros.get(macro.name) is not macro:
            raise _Unsafe()
        uses = _loads(self.tree, macro.name)
        if self.writes[macro.name] or len(uses) != 1:
            raise _Unsafe()
        call, field, _ = self.parents[id(uses[0])]
        if not isinstance(call, nodes.Call) or field != "node" or call.dyn_args or call.dyn_kwargs:
            raise _Unsafe()
        if len(call.args) > len(macro.args) or len({item.key for item in call.kwargs}) != len(call.kwargs):
            raise _Unsafe()
        names = [arg.name for arg in macro.args]
        values = dict(zip(names[-len(macro.defaults):], macro.defaults)) if macro.defaults else {}
        values.update(zip(names, call.args))
        for item in call.kwargs:
            if item.key not in names or item.key in names[:len(call.args)]:
                raise _Unsafe()
            values[item.key] = item.value
        return call, values

    def stable(self, node: nodes.Node, parameters: dict[str, nodes.Expr], seen=frozenset()) -> bool:
        if len(seen) > 64:
            return False
        if isinstance(node, nodes.Name):
            if node.name in seen:
                return False
            value = parameters.get(node.name)
            if value is not None:
                return self.stable(value, {}, seen | {node.name})
            if self.writes[node.name] > 1:
                return False
            value = self.bindings.get(node.name)
            if value is not None:
                return self.stable(value, parameters, seen | {node.name})
            return self.writes[node.name] == 0
        if isinstance(node, nodes.Call):
            return False
        if isinstance(node, nodes.Filter) and node.name not in {
            "abs", "capitalize", "float", "format", "int", "length", "lower", "replace",
            "round", "string", "title", "trim", "upper", "regex_replace", "regex_search",
        }:
            return False
        return all(self.stable(child, parameters, seen) for child in node.iter_child_nodes())

    def top_level(self, node: nodes.Node) -> nodes.Node:
        while id(node) in self.parents and self.parents[id(node)][0] is not self.tree:
            node = self.parents[id(node)][0]
        return node

    def guarded(self, target: nodes.Node, stack=frozenset()) -> bool:
        guards: list[nodes.Node] = []
        parameters: dict[str, nodes.Expr] = {}
        nested_guard = False
        node = target
        while id(node) in self.parents:
            parent, field, position = self.parents[id(node)]
            if isinstance(parent, nodes.If):
                if field == "body":
                    guards.append(parent.test)
                elif field in {"else_", "elif_"}:
                    guards.append(parent.test)
                    if field == "elif_":
                        guards.extend(item.test for item in parent.elif_[:position])
                    if field == "else_":
                        guards.extend(item.test for item in parent.elif_)
            elif isinstance(parent, nodes.CondExpr) and field in {"expr1", "expr2"}:
                guards.append(parent.test)
            elif isinstance(parent, (nodes.And, nodes.Or)) and field == "right":
                guards.append(parent.left)
            elif isinstance(parent, (nodes.Assign, nodes.AssignBlock)):
                if not isinstance(parent.target, nodes.Name) or not _loads(self.tree, parent.target.name):
                    raise _Unsafe()  # Do not infer intent from a dead value.
            elif isinstance(parent, nodes.Macro):
                if parent.name in stack:
                    raise _Unsafe()
                call, parameters = self.invocation(parent)
                nested_guard = self.guarded(call, stack | {parent.name})
            elif isinstance(parent, (nodes.For, nodes.CallBlock, nodes.With)):
                # Their scoping/evaluation counts are outside the bounded rewrite.
                raise _Unsafe()
            node = parent
        return (nested_guard or bool(guards)) and all(self.stable(guard, parameters) for guard in guards)


def _single_assignment(source, tree, key, environment, context):
    calls = [n for n in tree.find_all(nodes.Filter) if _index(n, key)]
    if len(calls) != 1:
        return None
    assignments = [n for n in tree.body if isinstance(n, nodes.Assign) and isinstance(n.target, nodes.Name)]
    current = next((n for n in assignments if calls[0] in _all(n.node, nodes.Filter)), None)
    if current is None or not _movable(current.node, key):
        return None
    replacement = deepcopy(current.node)
    removed = []
    for _ in range(32):
        name = current.target.name
        if context.writes[name] != 1 or name in context.macros:
            return None
        uses = _loads(tree, name)
        if len(uses) != 1:
            return None
        removed.append(current)
        use = uses[0]
        consumer = next((n for n in assignments if use in _all(n.node, nodes.Name)), None)
        if consumer is not None:
            if tree.body.index(consumer) <= tree.body.index(current):
                return None
            combined = _replaced(consumer.node, {id(use): replacement})
            if _movable(combined, key):
                current, replacement = consumer, combined
                continue
        if tree.body.index(context.top_level(use)) <= tree.body.index(current) or not context.guarded(use):
            return None
        # Never move a global declaration into a macro defined before the binding.
        enclosing = use
        while id(enclosing) in context.parents:
            enclosing = context.parents[id(enclosing)][0]
            if isinstance(enclosing, nodes.Macro) and tree.body.index(enclosing) < tree.body.index(current):
                return None
        edits = _Edits(source, tree, environment)
        changes = {id(use): replacement}
        edits.expressions(changes)
        for declaration in removed:
            edits.remove(declaration)
            changes[id(declaration)] = None
        return edits.finish(_replaced(tree, changes))
    return None


def _macro_argument(source, tree, key, environment, context):
    for macro in context.macros.values():
        try:
            call, parameters = context.invocation(macro)
        except _Unsafe:
            continue
        if macro.defaults or any(_loads(macro, name) for name in ("caller", "varargs", "kwargs")):
            continue
        for index, parameter in enumerate(macro.args):
            value = parameters.get(parameter.name)
            if value is None:
                continue
            removed = []
            # A single-use closed alias passed at the call site is equally safe
            # to specialize. Do not substitute episode inputs or other arguments.
            for _ in range(32):
                names = list(value.find_all(nodes.Name)) if not isinstance(value, nodes.Name) else [value]
                if not names:
                    break
                replacements = {}
                for name in names:
                    binding = next((n for n in tree.body if isinstance(n, nodes.Assign) and isinstance(n.target, nodes.Name) and n.target.name == name.name), None)
                    if binding is None or context.writes[name.name] != 1 or len(_loads(tree, name.name)) != 1:
                        break
                    if tree.body.index(binding) >= tree.body.index(context.top_level(call)):
                        break
                    replacements[id(name)] = binding.node
                    removed.append(binding)
                if len(replacements) != len(names):
                    break
                value = _replaced(value, replacements)
            if not any(_index(n, key) for n in _all(value, nodes.Filter)) or not _movable(value, key):
                continue
            uses = _loads(tree, parameter.name)
            if context.writes[parameter.name] != 1 or len(uses) != 1 or not context.guarded(uses[0]):
                continue
            revised_macro = deepcopy(macro)
            revised_macro.args.pop(index)
            revised_macro.body = _replaced(nodes.Template(macro.body), {id(uses[0]): value}).body
            revised_call = deepcopy(call)
            if index < len(call.args):
                revised_call.args.pop(index)
            else:
                revised_call.kwargs = [item for item in revised_call.kwargs if item.key != parameter.name]
            edits = _Edits(source, tree, environment)
            edits.expressions({id(uses[0]): value, id(call): revised_call})
            edits.macro(macro, revised_macro)
            changes = {id(macro): revised_macro, id(call): revised_call}
            for declaration in removed:
                edits.remove(declaration)
                changes[id(declaration)] = None
            return edits.finish(_replaced(tree, changes))
    return None


def _container_lookup(source, tree, key, environment, context):
    """Make literal-table selection lazy without dropping other computations.

    Named tables keep every non-index entry at its original evaluation site.
    Only the index slot becomes a placeholder, and all reads of that slot are
    rewritten. Inline tables are limited to constants/already-bound scalar reads.
    """
    for container in tree.find_all((nodes.List, nodes.Tuple, nodes.Dict)):
        if not any(_index(n, key) for n in container.find_all(nodes.Filter)):
            continue
        if isinstance(container, nodes.Dict):
            if not all(isinstance(pair.key, nodes.Const) and type(pair.key.value) in {str, int, bool} for pair in container.items):
                continue
            entries = [(pair.key.value, pair.value) for pair in container.items]
            if len({k for k, _ in entries}) != len(entries):
                continue
            values = dict(entries)
        else:
            values = dict(enumerate(container.items))
        indexed = {k for k, value in values.items() if any(_index(n, key) for n in _all(value, nodes.Filter))}
        if len(indexed) != 1 or not all(_movable(values[k], key) for k in indexed):
            continue
        parent, field, _ = context.parents[id(container)]
        declaration = parent if isinstance(parent, nodes.Assign) and parent in tree.body and field == "node" else None
        if declaration is not None:
            if not isinstance(declaration.target, nodes.Name) or context.writes[declaration.target.name] != 1:
                continue
            references = _loads(tree, declaration.target.name)
            lookups = []
            for reference in references:
                lookup, role, _ = context.parents[id(reference)]
                if not isinstance(lookup, nodes.Getitem) or role != "node":
                    break
                lookups.append(lookup)
            if len(lookups) != len(references) or not lookups:
                continue
            if any(tree.body.index(context.top_level(lookup)) <= tree.body.index(declaration) for lookup in lookups):
                continue
            # A mutable/aliased container is never specialized; every observer
            # must be one of these explicitly checked literal-key selections.
            if any(any(isinstance(n, nodes.Macro) for n in _ancestors(context, lookup)) for lookup in lookups):
                continue
        elif isinstance(parent, nodes.Getitem) and field == "node":
            lookups = [parent]
            def scalar_read(value):
                if _movable(value, key):
                    return True
                if isinstance(value, nodes.Name):
                    if context.writes[value.name] == 0:
                        return True  # WireLoft supplies media input values as text.
                    binding = next((n for n in tree.body if isinstance(n, nodes.Assign) and isinstance(n.target, nodes.Name) and n.target.name == value.name), None)
                    return binding is not None and context.writes[value.name] == 1 and tree.body.index(binding) < tree.body.index(context.top_level(container))
                return isinstance(value, nodes.Concat) and all(scalar_read(n) for n in value.nodes)
            if not all(scalar_read(value) for value in values.values()):
                continue
        else:
            continue

        def boolean(selector, seen=frozenset()):
            if isinstance(selector, (nodes.Compare, nodes.Not, nodes.Test)):
                return True
            if isinstance(selector, nodes.Const):
                return type(selector.value) is bool
            if isinstance(selector, (nodes.And, nodes.Or)):
                return boolean(selector.left, seen) and boolean(selector.right, seen)
            if isinstance(selector, nodes.Name) and selector.name not in seen and context.writes[selector.name] == 1:
                value = context.bindings.get(selector.name)
                return value is not None and boolean(value, seen | {selector.name})
            return False

        def select(selector, lookup):
            if isinstance(selector, nodes.Const) and type(selector.value) in {str, int, bool}:
                if not isinstance(container, nodes.Dict) and type(selector.value) is not int:
                    raise _Unsafe()
                if selector.value not in values:
                    raise _Unsafe()
                if declaration is not None and selector.value not in indexed:
                    return nodes.Getitem(deepcopy(lookup.node), deepcopy(selector), "load")
                return deepcopy(values[selector.value])
            if isinstance(selector, nodes.CondExpr) and selector.expr2 is not None and context.stable(selector.test, {}):
                return nodes.CondExpr(deepcopy(selector.test), select(selector.expr1, lookup), select(selector.expr2, lookup))
            if isinstance(container, nodes.Dict) and set(values) == {True, False} and boolean(selector) and context.stable(selector, {}):
                return nodes.CondExpr(deepcopy(selector), select(nodes.Const(True), lookup), select(nodes.Const(False), lookup))
            raise _Unsafe()

        changes = {id(lookup): select(lookup.arg, lookup) for lookup in lookups}
        if declaration is not None:
            changes.update({id(values[k]): nodes.Const(None) for k in indexed})
        expected = _replaced(tree, changes)
        checked = _Context(expected)
        index_calls = [n for n in expected.find_all(nodes.Filter) if _index(n, key)]
        if len(index_calls) != 1 or not checked.guarded(index_calls[0]):
            continue
        edits = _Edits(source, tree, environment)
        edits.expressions(changes)
        return edits.finish(expected)
    return None


def _ancestors(context: _Context, node: nodes.Node):
    while id(node) in context.parents:
        node = context.parents[id(node)][0]
        yield node


def suggest_guarded_index(source: str, tree: nodes.Template, key: str, environment: Environment) -> CustomIndexSuggestion | None:
    """Try independent bounded proofs. Uncertainty is advice withheld, not an error."""
    if len([node for node in tree.find_all(nodes.Filter) if _index(node, key)]) != 1:
        return None
    if any(tree.find_all((nodes.Import, nodes.FromImport, nodes.Include, nodes.Extends))):
        return None
    try:
        context = _Context(tree)
    except _Unsafe:
        return None
    for strategy in (_single_assignment, _macro_argument, _container_lookup):
        try:
            result = strategy(source, tree, key, environment, context)
            if result is not None:
                return result
        except (_Unsafe, TemplateError, RecursionError, KeyError, TypeError, ValueError):
            continue
    return None
