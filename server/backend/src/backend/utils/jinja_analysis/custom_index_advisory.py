"""Read-only Custom Index diagnostics and optional, user-applied Jinja refactors.

This module helps generate advisory replacement Jinja code if it detects the
user might be creating unintentional side-effects or other obvious improvements
could be made.

Unknown syntax/data flow means no suggestion, it does not mean the Jinja is
faulty and therefore WireLoft simply omits a suggestion in this case.
"""
from __future__ import annotations

from collections import Counter
from copy import deepcopy
from dataclasses import dataclass
from typing import Iterable, Literal

from jinja2 import Environment, TemplateError, nodes
from jinja2.visitor import NodeTransformer

from .expressions import expression_key


@dataclass(frozen=True)
class CustomIndexSuggestion:
    before: str
    after: str
    output_template: str


CustomIndexAdvisoryKind = Literal["all_episodes", "episode_index"]


@dataclass(frozen=True)
class CustomIndexAdvisory:
    key: str
    message: str
    kind: CustomIndexAdvisoryKind = "all_episodes"
    suggestion: CustomIndexSuggestion | None = None


@dataclass(frozen=True)
class CustomIndexAdvisoryResult:
    advisories: tuple[CustomIndexAdvisory, ...] = ()
    # Editing incomplete Jinja is normal. The preview already owns error display.
    error: str | None = None


class _Uncertain(Exception):
    pass


def _index_key(node: nodes.Node) -> str | None:
    if (
        isinstance(node, nodes.Filter) and node.name == "custom_index"
        and isinstance(node.node, nodes.Const) and isinstance(node.node.value, str)
        and not (node.args or node.kwargs or node.dyn_args or node.dyn_kwargs)
    ):
        return node.node.value
    return None


def _names(node: nodes.Node, context: str = "load") -> set[str]:
    return {
        item.name for item in (node, *node.find_all(nodes.Name))
        if isinstance(item, nodes.Name) and item.ctx == context
    }


class _MustRun:
    """A lower bound on keys reached in every successful native Jinja render.

    Branches intersect guarantees; sequential statements union them. Unknown
    loops/calls contribute no guarantees, but cannot erase an unrelated known
    call. This intentionally does not evaluate filters, methods or sample data.
    """

    def __init__(self, tree: nodes.Template):
        definitions = list(tree.find_all(nodes.Macro))
        counts = Counter(item.name for item in definitions)
        writes = _names(tree, "store") | _names(tree, "param")
        self.macros = {
            item.name: item for item in tree.body
            if isinstance(item, nodes.Macro) and counts[item.name] == 1
            and item.name not in writes
        }
        self.stack: set[str] = set()
        self.steps = 8192

    def body(self, body: Iterable[nodes.Node]) -> set[str]:
        result: set[str] = set()
        for statement in body:
            result.update(self.visit(statement))
        return result

    def visit(self, node: nodes.Node | None) -> set[str]:
        self.steps -= 1
        if self.steps < 0:
            raise _Uncertain("Advisory analysis reached its work limit")
        if node is None or isinstance(node, (nodes.Macro, nodes.Import, nodes.FromImport, nodes.Include, nodes.Extends)):
            return set()
        if isinstance(node, nodes.If):
            otherwise = node.else_
            # elif tests execute only after preceding tests fail.
            alternative = self.body(otherwise)
            for branch in reversed(node.elif_):
                alternative = self.visit(branch.test) | (self.body(branch.body) & alternative)
            if isinstance(node.test, nodes.Const):
                branch = self.body(node.body) if node.test.value else alternative
                return self.visit(node.test) | branch
            return self.visit(node.test) | (self.body(node.body) & alternative)
        if isinstance(node, nodes.CondExpr):
            if isinstance(node.test, nodes.Const):
                return self.visit(node.expr1 if node.test.value else node.expr2)
            return self.visit(node.test) | (self.visit(node.expr1) & self.visit(node.expr2))
        if isinstance(node, (nodes.And, nodes.Or)):
            result = self.visit(node.left)
            if isinstance(node.left, nodes.Const) and bool(node.left.value) == isinstance(node, nodes.And):
                result.update(self.visit(node.right))
            return result
        if isinstance(node, nodes.Compare):
            # Later terms of a chained comparison can be skipped by Jinja.
            return self.visit(node.expr) | (self.visit(node.ops[0].expr) if node.ops else set())
        if isinstance(node, nodes.For):
            result = self.visit(node.iter)
            # No data-dependent iteration count is guessed, even from a preview.
            if node.test is None and not node.recursive and isinstance(node.iter, (nodes.List, nodes.Tuple)):
                result.update(self.body(node.body if node.iter.items else node.else_))
            return result
        if isinstance(node, nodes.CallBlock):
            # caller() may never be invoked by the callee.
            return self.visit(node.call)
        if isinstance(node, nodes.Call):
            result = self.body(node.iter_child_nodes())
            if isinstance(node.node, nodes.Name) and node.node.name in self.macros:
                name = node.node.name
                if name not in self.stack:
                    self.stack.add(name)
                    try:
                        result.update(self.body(self.macros[name].body))
                    finally:
                        self.stack.remove(name)
            return result
        if isinstance(node, nodes.Block):
            return set()  # Inheritance can replace or defer the block.
        result = self.body(node.iter_child_nodes())
        key = _index_key(node)
        if key is not None:
            result.add(key)
        return result


@dataclass(frozen=True)
class _StatementSource:
    start: int
    end: int
    source: str


def _assignment_sources(source: str, environment: Environment) -> dict[str, _StatementSource]:
    """Locate exact set-tag spans using Jinja's lexer, not regex over the code.

    Whitespace-control/newline normalization may discard lexer characters. In
    that case omit a refactor rather than risk an incorrect source edit.
    """
    tokens = list(environment.lex(source))
    if "".join(value for _, _, value in tokens) != source:
        raise _Uncertain("Source locations could not be preserved")
    result: dict[str, _StatementSource] = {}
    duplicates: set[str] = set()
    offset = 0
    start: int | None = None
    for _, kind, value in tokens:
        if kind == "block_begin":
            start = offset
        offset += len(value)
        if kind == "block_end" and start is not None:
            fragment = source[start:offset]
            # Most block openers are not standalone templates. Only a simple
            # assignment is useful here; parse failures are expected.
            if fragment[2:-2].lstrip().startswith("set "):
                try:
                    parsed = environment.parse(fragment)
                except TemplateError:
                    continue
                if len(parsed.body) == 1 and isinstance(parsed.body[0], nodes.Assign):
                    target = parsed.body[0].target
                    if isinstance(target, nodes.Name):
                        if target.name in result:
                            duplicates.add(target.name)
                        result[target.name] = _StatementSource(start, offset, fragment)
            start = None
    return {name: span for name, span in result.items() if name not in duplicates}


def _assignment_block_sources(source: str, environment: Environment) -> dict[str, _StatementSource]:
    """Locate complete set/endset spans without formatting the source."""
    tokens = list(environment.lex(source))
    if "".join(value for _, _, value in tokens) != source:
        raise _Uncertain("Source locations could not be preserved")

    tags: list[_StatementSource] = []
    offset = 0
    start: int | None = None
    for _, kind, value in tokens:
        if kind == "block_begin":
            start = offset
        offset += len(value)
        if kind == "block_end" and start is not None:
            tags.append(_StatementSource(start, offset, source[start:offset]))
            start = None

    result: dict[str, _StatementSource] = {}
    duplicates: set[str] = set()
    stack: list[tuple[str, int]] = []
    for tag in tags:
        tag_tokens = list(environment.lex(tag.source))
        keyword = next((value for _, kind, value in tag_tokens if kind == "name"), "")
        if keyword == "set":
            try:
                parsed = environment.parse(tag.source + "{% endset %}")
            except TemplateError:
                continue
            if len(parsed.body) == 1 and isinstance(parsed.body[0], nodes.AssignBlock):
                target = parsed.body[0].target
                if isinstance(target, nodes.Name):
                    stack.append((target.name, tag.start))
            continue
        if keyword != "endset" or not stack:
            continue
        name, block_start = stack.pop()
        span = _StatementSource(block_start, tag.end, source[block_start:tag.end])
        if name in result:
            duplicates.add(name)
        result[name] = span

    return {name: span for name, span in result.items() if name not in duplicates}


def _name_token_spans(
    source: str,
    environment: Environment,
    *,
    name: str,
    within: _StatementSource,
) -> tuple[tuple[int, int], ...]:
    """Return exact lexer spans for a name inside one already-located block."""
    result: list[tuple[int, int]] = []
    offset = 0
    for _, kind, value in environment.lex(source):
        start = offset
        offset += len(value)
        if kind == "name" and value == name and within.start <= start < within.end:
            result.append((start, offset))
    return tuple(result)


# Only expressions whose original value and evaluation count can be retained by
# the small suggested refactor. This list is NOT a template-language restriction.
_SAFE_FILTERS = frozenset({
    "abs", "capitalize", "float", "format", "int", "length", "lower", "replace",
    "round", "string", "title", "trim", "upper", "regex_replace", "regex_search",
})


def _expression_source(node: nodes.Expr) -> str:
    """Print the small expression subset used by suggestions, never runtime code."""
    if isinstance(node, nodes.Const):
        if node.value is None:
            return "none"
        if isinstance(node.value, bool):
            return "true" if node.value else "false"
        if isinstance(node.value, (str, int, float)):
            return repr(node.value)
    if isinstance(node, nodes.Name):
        return node.name
    if isinstance(node, nodes.Concat):
        return " ~ ".join(f"({_expression_source(item)})" for item in node.nodes)
    if isinstance(node, nodes.Filter):
        if node.name not in _SAFE_FILTERS and _index_key(node) is None:
            raise _Uncertain("The expression may have side effects")
        if node.dyn_args or node.dyn_kwargs:
            raise _Uncertain("Dynamic arguments")
        args = [_expression_source(item) for item in node.args]
        args.extend(f"{item.key}={_expression_source(item.value)}" for item in node.kwargs)
        call = f"({', '.join(args)})" if args else ""
        operand = _expression_source(node.node)
        if not isinstance(node.node, (nodes.Const, nodes.Name, nodes.Filter)):
            operand = f"({operand})"
        return f"{operand} | {node.name}{call}"
    if isinstance(node, nodes.Compare):
        operators = {"eq": "==", "ne": "!=", "lt": "<", "lteq": "<=", "gt": ">", "gteq": ">=", "in": "in", "notin": "not in"}
        return " ".join([f"({_expression_source(node.expr)})", *(
            f"{operators[item.op]} ({_expression_source(item.expr)})" for item in node.ops
        )])
    if isinstance(node, (nodes.And, nodes.Or)):
        op = "and" if isinstance(node, nodes.And) else "or"
        return f"({_expression_source(node.left)}) {op} ({_expression_source(node.right)})"
    if isinstance(node, nodes.Not):
        return f"not ({_expression_source(node.node)})"
    raise _Uncertain(f"No safe suggested source for {type(node).__name__}")


def _string_expression(node: nodes.Expr, strings: set[str] | frozenset[str] = frozenset()) -> bool:
    return (
        isinstance(node, nodes.Concat)
        or isinstance(node, nodes.Const) and isinstance(node.value, str)
        or isinstance(node, nodes.Name) and node.name in strings
        or isinstance(node, nodes.Filter) and node.name in {
            "capitalize", "format", "lower", "replace", "string", "title", "trim", "upper", "regex_replace",
        }
    )


def _captured_output(node: nodes.Expr, strings: set[str]) -> str:
    if isinstance(node, nodes.Concat):
        return "".join(_captured_output(item, strings) for item in node.nodes)
    if isinstance(node, nodes.Const) and isinstance(node.value, str):
        # Literal template delimiters/newlines would change a capture's meaning.
        if any(part in node.value for part in ("{{", "{%", "{#", "\n", "\r", "\x00")):
            raise _Uncertain("Literal text needs escaping")
        return node.value
    value = _expression_source(node)
    # Concat stringifies None and other non-strings before finalization. Preserve
    # that conversion when splitting a concat into individual output fragments.
    if not _string_expression(node, strings) and _index_key(node) is None:
        value = f"({value}) | string"
    return "{{ " + value + " }}"


class _Inline(NodeTransformer):
    def __init__(self, name: str, value: nodes.Expr):
        self.name, self.value = name, value

    def visit_Name(self, node: nodes.Name, *args, **kwargs):
        return self.value if node.ctx == "load" and node.name == self.name else node


def _reaches_output(tree: nodes.Template, name: str) -> bool:
    needed = {name}
    for _ in range(64):
        previous = set(needed)
        for statement in tree.body:
            if isinstance(statement, nodes.Output) and _names(statement) & needed:
                return True
            if isinstance(statement, nodes.Assign) and isinstance(statement.target, nodes.Name) and _names(statement.node) & needed:
                needed.add(statement.target.name)
        if needed == previous:
            return False
    return False


def _is_direct_output_value(tree: nodes.Template, name: str) -> bool:
    """Whether a variable's only load is a plain output expression."""
    loads = [
        item for item in tree.find_all(nodes.Name)
        if item.ctx == "load" and item.name == name
    ]
    if len(loads) != 1:
        return False
    return any(
        isinstance(statement, nodes.Output)
        and any(
            isinstance(item, nodes.Name) and item.ctx == "load" and item.name == name
            for item in statement.nodes
        )
        for statement in tree.body
    )


def _stable_guard(expression: nodes.Expr, declarations: list[nodes.Assign], writes: Counter, before: nodes.Assign) -> bool:
    """Do not recommend a random/index-dependent guard hidden behind aliases."""
    by_name = {item.target.name: item for item in declarations[:declarations.index(before)]}
    pending = [expression]
    seen: set[str] = set()
    budget = 2048
    while pending:
        budget -= 1
        if budget < 0:
            return False
        node = pending.pop()
        if isinstance(node, nodes.Call):
            return False
        if isinstance(node, nodes.Filter) and node.name not in _SAFE_FILTERS:
            return False
        if isinstance(node, nodes.Name):
            if writes[node.name] > 1:
                return False
            binding = by_name.get(node.name)
            if binding is not None and node.name not in seen:
                seen.add(node.name)
                pending.append(binding.node)
        pending.extend(node.iter_child_nodes())
    return True


def _suggest_assignment_block_use(
    source: str,
    tree: nodes.Template,
    *,
    key: str,
    environment: Environment,
    current: nodes.Assign,
    replacement: nodes.Expr,
    removed: list[nodes.Assign],
    writes: Counter,
) -> CustomIndexSuggestion | None:
    """Inline one eager index chain into an existing conditional set block.

    The set block itself stays untouched except for the single variable load.
    Jinja therefore remains responsible for every if/elif/else rule.
    """
    name = current.target.name
    candidates = [
        item for item in tree.body
        if isinstance(item, nodes.AssignBlock) and name in _names(item)
    ]
    if len(candidates) != 1:
        return None
    block = candidates[0]
    if not isinstance(block.target, nodes.Name):
        return None
    if writes[block.target.name] != 1 or not _reaches_output(tree, block.target.name):
        return None

    current_index = tree.body.index(current)
    block_index = tree.body.index(block)
    if block_index <= current_index:
        return None

    # Inlining inside an arbitrary Jinja block could otherwise change the
    # meaning of free variables through loop/with/macro shadowing. Formatting
    # chains around the Custom Index itself remain fine.
    if _names(replacement):
        return None

    assignment_sources = _assignment_sources(source, environment)
    if any(item.target.name not in assignment_sources for item in removed):
        return None
    block_sources = _assignment_block_sources(source, environment)
    block_source = block_sources.get(block.target.name)
    if block_source is None:
        return None

    references = _name_token_spans(
        source, environment, name=name, within=block_source,
    )
    if len(references) != 1:
        return None

    replacement_source = _expression_source(replacement)
    reference_start, reference_end = references[0]
    revised_block = (
        source[block_source.start:reference_start]
        + replacement_source
        + source[reference_end:block_source.end]
    )

    edits: list[tuple[int, int, str]] = [
        (assignment_sources[item.target.name].start, assignment_sources[item.target.name].end, "")
        for item in removed
    ]
    edits.append((reference_start, reference_end, replacement_source))
    revised = source
    for start, end, text in sorted(edits, reverse=True):
        revised = revised[:start] + text + revised[end:]
    if len(revised) > 4096:
        return None

    parsed = environment.parse(revised)
    if key in _MustRun(parsed).body(parsed.body):
        return None

    return CustomIndexSuggestion(
        before="\n".join([
            *(assignment_sources[item.target.name].source for item in removed),
            block_source.source,
        ]),
        after=revised_block,
        output_template=revised,
    )


def _suggest(source: str, tree: nodes.Template, key: str, environment: Environment) -> CustomIndexSuggestion | None:
    """Move a single-use assignment chain into its existing selected branch.

    Do not infer a new predicate from names such as 'extra'. Only reuse a guard
    already present in the author's code. Ambiguous uses/scope/type => no fix.
    """
    sources = _assignment_sources(source, environment)
    writes = Counter(item.name for item in tree.find_all(nodes.Name) if item.ctx in {"store", "param"})
    references = Counter(item.name for item in tree.find_all(nodes.Name) if item.ctx == "load")
    calls = [item for item in tree.find_all(nodes.Filter) if _index_key(item) == key]
    if len(calls) != 1:
        return None
    declarations = [item for item in tree.body if isinstance(item, nodes.Assign) and isinstance(item.target, nodes.Name)]
    producer = next((item for item in declarations if item.node is calls[0]), None)
    if producer is None:
        return None

    strings: set[str] = set()
    for item in declarations:
        if writes[item.target.name] == 1 and _string_expression(item.node, strings):
            strings.add(item.target.name)
    removed = [producer]
    current = producer
    replacement = deepcopy(producer.node)
    for _ in range(32):
        name = current.target.name
        if writes[name] != 1 or references[name] != 1 or name not in sources:
            return None
        consumer = next((item for item in declarations if name in _names(item.node)), None)
        if consumer is None:
            return _suggest_assignment_block_use(
                source,
                tree,
                key=key,
                environment=environment,
                current=current,
                replacement=replacement,
                removed=removed,
                writes=writes,
            )
        if tree.body.index(consumer) <= tree.body.index(current):
            return None
        if writes[consumer.target.name] != 1 or consumer.target.name not in sources:
            return None
        # Moving a computation past a rebinding would change its value.
        start, end = tree.body.index(current), tree.body.index(consumer)
        inputs = _names(replacement)
        if any(_names(item, "store") & inputs for item in tree.body[start + 1:end]):
            return None
        expression = consumer.node
        if isinstance(expression, nodes.CondExpr):
            if name in _names(expression.test):
                return None
            yes = name in _names(expression.expr1)
            no = expression.expr2 is not None and name in _names(expression.expr2)
            if yes == no or not _reaches_output(tree, consumer.target.name):
                return None

            implicit_else = expression.expr2 is None
            if implicit_else:
                # A no-else inline conditional yields Jinja Undefined when false.
                # An empty captured set is render-equivalent only when this value
                # is emitted directly and is not otherwise inspected downstream.
                if not yes or not _is_direct_output_value(tree, consumer.target.name):
                    return None
                if not _string_expression(expression.expr1):
                    return None
            else:
                # Keep captures string-valued. An unknown/numeric result needs a
                # different refactor; do not silently change its Jinja value type.
                if not (_string_expression(expression.expr1) and _string_expression(expression.expr2)):
                    return None

            if not _stable_guard(expression.test, declarations, writes, consumer):
                return None
            guard = _expression_source(expression.test)
            parsed_guard = environment.parse("{{ " + guard + " }}").body[0].nodes[0]
            if expression_key(parsed_guard) != expression_key(expression.test):
                return None
            first = _Inline(name, replacement).visit(deepcopy(expression.expr1))
            if implicit_else:
                body = (
                    "{% set " + consumer.target.name + " %}{% if " + guard + " %}"
                    + _captured_output(first, strings)
                    + "{% endif %}{% endset %}"
                )
            else:
                second = _Inline(name, replacement).visit(deepcopy(expression.expr2))
                body = (
                    "{% set " + consumer.target.name + " %}{% if " + guard + " %}"
                    + _captured_output(first, strings) + "{% else %}" + _captured_output(second, strings)
                    + "{% endif %}{% endset %}"
                )
            edits = [(sources[item.target.name], "") for item in removed]
            edits.append((sources[consumer.target.name], body))
            revised = source
            for span, text in sorted(edits, key=lambda item: item[0].start, reverse=True):
                revised = revised[:span.start] + text + revised[span.end:]
            if len(revised) > 4096:
                return None
            parsed = environment.parse(revised)
            if key in _MustRun(parsed).body(parsed.body):
                return None  # A constant/otherwise unconditional guard would not help.
            return CustomIndexSuggestion(
                before="\n".join(sources[item.target.name].source for item in [*removed, consumer]),
                after=body,
                output_template=revised,
            )
        # Follow ordinary one-use aliases/formatting rather than special-casing
        # a name or a Plex layout. The serializer doubles as a conservative gate.
        _expression_source(expression)
        replacement = _Inline(name, replacement).visit(deepcopy(expression))
        _expression_source(replacement)
        removed.append(consumer)
        current = consumer
    return None


def _unconditional_output_keys(tree: nodes.Template) -> set[str]:
    """Recognize unconditional output use, not merely an eager declaration.

    Follow ordinary aliases/formatting, then exclude keys connected to any
    conditional or uncertain scope. Unrelated Jinja cannot disqualify a key.
    This is an advisory-only intent heuristic, never a rendering rule.
    """
    bindings: dict[str, set[str]] = {}

    def keys(node: nodes.Node) -> set[str]:
        found = {
            key for item in (node, *node.find_all(nodes.Filter))
            if (key := _index_key(item)) is not None
        }
        for name in _names(node):
            found.update(bindings.get(name, ()))
        return found

    declarations = [
        item for item in tree.body
        if isinstance(item, nodes.Assign) and isinstance(item.target, nodes.Name)
    ]
    # Union across writes is intentional: ambiguous rebinding can only suppress
    # this recommendation, not hide a conditional downstream use.
    for _ in range(64):
        changed = False
        for item in declarations:
            old = bindings.setdefault(item.target.name, set())
            before = len(old)
            old.update(keys(item.node))
            changed |= len(old) != before
        if not changed:
            break
    else:
        return set()

    uncertain: set[str] = set()
    writes = Counter(item.name for item in tree.find_all(nodes.Name) if item.ctx in {"store", "param"})
    for name, dependencies in bindings.items():
        if writes[name] != 1:
            uncertain.update(dependencies)
    # Do not try to infer intent through runtime-selected scopes or opaque
    # calls carrying an index. A title.replace() elsewhere is irrelevant.
    for item in tree.find_all((
        nodes.If, nodes.CondExpr, nodes.And, nodes.Or, nodes.Compare,
        nodes.For, nodes.With, nodes.Macro, nodes.AssignBlock, nodes.CallBlock,
        nodes.Call, nodes.Block, nodes.Import, nodes.FromImport, nodes.Include,
    )):
        uncertain.update(keys(item))
    output = set().union(*(
        keys(item) for item in tree.body if isinstance(item, (nodes.Output, nodes.FilterBlock))
    ))
    return output - uncertain


def _suggest_episode_index(
    source: str, tree: nodes.Template, key: str, environment: Environment,
) -> CustomIndexSuggestion | None:
    """Replace literal calls, preserving unrelated source and integer semantics."""
    shadowed = _names(tree, "store") | _names(tree, "param")
    shadowed.update(item.name for item in tree.find_all(nodes.Macro))
    shadowed.update(item.target for item in tree.find_all(nodes.Import))
    for item in tree.find_all(nodes.FromImport):
        shadowed.update(name[1] if isinstance(name, tuple) else name for name in item.names)
    if "episode_index" in shadowed:
        return None  # The built-in variable would be shadowed by user code.
    tokens = list(environment.lex(source))
    if "".join(value for _, _, value in tokens) != source:
        return None
    significant = []
    tags: list[tuple[int, int]] = []
    offset = 0
    start = None
    for _, kind, value in tokens:
        if kind in {"block_begin", "variable_begin"}:
            start = offset
        if kind != "whitespace":
            significant.append((kind, value, offset, offset + len(value)))
        offset += len(value)
        if kind in {"block_end", "variable_end"} and start is not None:
            tags.append((start, offset))
            start = None
    edits: list[tuple[int, int]] = []
    for a, b, c in zip(significant, significant[1:], significant[2:]):
        if a[0] != "string" or b[1] != "|" or c[0:2] != ("name", "custom_index"):
            continue
        fragment = source[a[2]:c[3]]
        parsed = environment.parse("{{ " + fragment + " }}")
        if _index_key(parsed.body[0].nodes[0]) == key:
            edits.append((a[2], c[3]))
    calls = [item for item in tree.find_all(nodes.Filter) if _index_key(item) == key]
    if not edits or len(edits) != len(calls):
        return None  # Parenthesized/unusual syntax is advice, not a guessed fix.

    def replace(start: int, end: int) -> str:
        fragment = source[start:end]
        for a, b in reversed(edits):
            if start <= a < b <= end:
                fragment = fragment[:a - start] + "(episode_index | int)" + fragment[b - start:]
        return fragment

    revised = replace(0, len(source))
    if len(revised) > 4096:
        return None
    environment.parse(revised)
    changed = [(a, b) for a, b in tags if any(a <= x < y <= b for x, y in edits)]
    return CustomIndexSuggestion(
        before="\n".join(source[a:b] for a, b in changed),
        after="\n".join(replace(a, b) for a, b in changed),
        output_template=revised,
    )


def get_custom_index_advisories(
    template: str, *, definition_keys: Iterable[str], environment: Environment,
) -> CustomIndexAdvisoryResult:
    """Analyze the current form only. Never load episodes or execute the template."""
    definitions = frozenset(definition_keys)
    if not definitions or not template:
        return CustomIndexAdvisoryResult()
    if len(template) > 4096:
        return CustomIndexAdvisoryResult(error="Output template is too long for advisory analysis")
    try:
        tree = environment.parse(template)
        # An external template could replace the entire program.
        if any(True for _ in tree.find_all(nodes.Extends)):
            return CustomIndexAdvisoryResult()
        guaranteed = _MustRun(tree).body(tree.body) & definitions
    except (TemplateError, _Uncertain, RecursionError) as exc:
        return CustomIndexAdvisoryResult(error=str(exc))
    unconditional = set()
    try:
        unconditional = _unconditional_output_keys(tree) & guaranteed
    except (_Uncertain, RecursionError):
        pass  # Unknown intent retains the original proven all-episode warning.
    advisories = []
    for key in sorted(guaranteed):
        suggestion = None
        try:
            suggestion = (
                _suggest_episode_index(template, tree, key, environment)
                if key in unconditional else _suggest(template, tree, key, environment)
            )
        except (TemplateError, _Uncertain, RecursionError, KeyError):
            pass  # A missing refactor must never hide a proven warning.
        advisories.append(CustomIndexAdvisory(
            key=key,
            kind="episode_index" if key in unconditional else "all_episodes",
            message=(
                "This Custom Index runs for every episode and has no conditional uses. "
                "Use WireLoft's episode_index variable for this show-wide numbering instead "
                "of maintaining a separate Custom Index. The stored episode index includes "
                "all episode types and can contain gaps, so review the preview before saving."
            ) if key in unconditional else (
                "Custom Indexes are designed to apply an index to only some episodes within a "
                "show. As currently setup, this Custom Index runs for every episode, "
                "even when its number is not used in the path. "
                "If you intend to use an all-episode sequence, you should probably use the "
                "{{\u00a0episode_index\u00a0}} variable WireLoft provides. "
                "To number only some episodes, put the custom_index call inside the condition "
                "that selects them."
            ),
            suggestion=suggestion,
        ))
    return CustomIndexAdvisoryResult(tuple(advisories))
