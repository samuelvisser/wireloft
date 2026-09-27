"""Infer the shared show directory from Jinja semantics, not a sample filename.

Only completed directory components independent of seasons/episodes qualify.
Volatile control-flow branches are considered even before those episodes exist.
Annotations are inserted *after* expression evaluation, never into filter inputs.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from itertools import product
import re
from typing import Callable, Mapping

from jinja2 import Environment, TemplateError, nodes
from jinja2.visitor import NodeTransformer

_SHOW, _ITEM = 1, 2
_ITEM_MARK, _SHOW_START, _SHOW_END = "\x01", "\x02", "\x03"
_SEASON_FOLDER = re.compile(r"^(?:s(?:eason)?[\W_]?\d+|specials|extras|trailers|featurettes)$", re.I)
_SHOW_VALUE = re.compile("\x02(.*?)\x03", re.S)
_MAX_BRANCH_VARIANTS = 64


@dataclass(frozen=True)
class ShowMediaDirectory:
    path: str | None
    reason: str | None = None


def _emitted_outputs(node: nodes.Node):
    # Captured blocks/macros are finalized as expressions, so their slashes
    # cannot create path structure in WireLoft's renderer.
    if isinstance(node, (nodes.Macro, nodes.Assign, nodes.AssignBlock)):
        return
    if isinstance(node, nodes.Output):
        yield node
    for child in node.iter_child_nodes():
        yield from _emitted_outputs(child)


def _trim_straight_line_filename(tree: nodes.Template) -> None:
    """Ignore arbitrarily complex filename-only logic after a proven boundary.

    Only trim a top-level Output. Trimming inside loops could remove assignments
    that affect a subsequent iteration's directory, so those stay conservative.
    """
    last = None
    for output in _emitted_outputs(tree):
        for index, expression in enumerate(output.nodes):
            if isinstance(expression, nodes.TemplateData) and "/" in expression.data:
                last = (output, index, expression.data.rfind("/") + 1)
    if last is None:
        return
    output, index, offset = last
    body_index = next((i for i, statement in enumerate(tree.body) if statement is output), None)
    if body_index is None:
        return
    output.nodes = [*output.nodes[:index], nodes.TemplateData(output.nodes[index].data[:offset])]
    tree.body = tree.body[:body_index + 1]


class _Dependencies:
    def __init__(self, tree: nodes.Template, values: Mapping[str, object], environment: Environment):
        self.bindings = {name: 0 for name in environment.globals}
        self.bindings.update({
            name: _SHOW if name in {"show", "show_title"} or name.startswith("meta_show_") else _ITEM
            for name in values
        })
        stores = {node.name for node in tree.find_all(nodes.Name) if node.ctx in {"store", "param"}}
        if stores & values.keys():
            raise ValueError("Show root cannot be inferred when built-in path variables are reassigned.")
        self.bindings.update({name: 0 for name in stores})
        self.bindings.update({node.name: 0 for node in tree.find_all(nodes.Macro)})
        # Fixed point includes indirect aliases and assignments made in branches.
        for _ in range(len(self.bindings) + 1):
            before = self.bindings.copy()
            self._scan(tree, 0)
            if self.bindings == before:
                break

    def mask(self, node: nodes.Node) -> int:
        if isinstance(node, nodes.Name):
            return self.bindings.get(node.name, _ITEM) if node.ctx == "load" else 0
        result = _ITEM if isinstance(node, nodes.Filter) and node.name in {"custom_index", "random"} else 0
        for child in node.iter_child_nodes():
            result |= self.mask(child)
        return result

    def _bind(self, target: nodes.Node, mask: int):
        if isinstance(target, (nodes.Name, nodes.NSRef)):
            self.bindings[target.name] = self.bindings.get(target.name, 0) | mask
        else:
            for child in target.iter_child_nodes():
                self._bind(child, mask)

    def _scan(self, node: nodes.Node, control: int):
        if isinstance(node, nodes.If):
            control |= self.mask(node.test)
        elif isinstance(node, nodes.For):
            control |= self.mask(node.iter)
            self._bind(node.target, control)
        elif isinstance(node, nodes.With):
            for target, value in zip(node.targets, node.values, strict=True):
                self._bind(target, self.mask(value) | control)
        elif isinstance(node, nodes.Assign):
            self._bind(node.target, self.mask(node.node) | control)
        elif isinstance(node, nodes.AssignBlock):
            self._bind(node.target, self.mask(node) | control)
        elif isinstance(node, nodes.Macro):
            self.bindings[node.name] |= self.mask(node) | control
        for child in node.iter_child_nodes():
            self._scan(child, control)


class _SymbolicOutput(NodeTransformer):
    def __init__(self, dependencies: _Dependencies, choices: tuple[bool, ...], *, collapse_branches: bool = False):
        self.dependencies = dependencies
        self.choices = choices
        self.collapse_branches = collapse_branches

    def visit_Output(self, node: nodes.Output, *args, **kwargs):
        output = []
        for expression in node.nodes:
            if isinstance(expression, nodes.TemplateData):
                output.append(expression)
                continue
            mask = self.dependencies.mask(expression)
            if mask & _ITEM:
                output.append(nodes.TemplateData(_ITEM_MARK))
            elif mask & _SHOW:
                output.extend([nodes.TemplateData(_SHOW_START), expression, nodes.TemplateData(_SHOW_END)])
            else:
                output.append(expression)
        return nodes.Output(output).set_lineno(node.lineno)

    def visit_If(self, node: nodes.If, *args, **kwargs):
        index = getattr(node, "_show_root_branch", None)
        if index is None and self.dependencies.mask(node.test) & _ITEM:
            # Only assignments remain; their aliases are already marked volatile.
            return nodes.Output([]).set_lineno(node.lineno)
        if index is not None and self.collapse_branches:
            return nodes.Output([nodes.TemplateData(_ITEM_MARK)]).set_lineno(node.lineno)
        if index is not None:
            node.test = nodes.Const(self.choices[index])
        return self.generic_visit(node, *args, **kwargs)

    def visit_Assign(self, node: nodes.Assign, *args, **kwargs):
        # Do not evaluate episode-dependent calculations just to infer a folder.
        if self.dependencies.mask(node.node) & _ITEM:
            node.node = self._empty_value(node.target)
        return node

    @staticmethod
    def _empty_value(target: nodes.Node) -> nodes.Expr:
        if isinstance(target, nodes.Tuple):
            return nodes.Tuple([_SymbolicOutput._empty_value(item) for item in target.items], "load")
        return nodes.Const("")

    def visit_With(self, node: nodes.With, *args, **kwargs):
        node.values = [
            self._empty_value(target) if self.dependencies.mask(value) & _ITEM else value
            for target, value in zip(node.targets, node.values, strict=True)
        ]
        return self.generic_visit(node, *args, **kwargs)

    def visit_AssignBlock(self, node: nodes.AssignBlock, *args, **kwargs):
        if self.dependencies.mask(node) & _ITEM:
            return nodes.Assign(node.target, self._empty_value(node.target)).set_lineno(node.lineno)
        # Captured text must not carry annotations through arbitrary filters.
        return node

    def visit_Macro(self, node: nodes.Macro, *args, **kwargs):
        # A macro call is annotated as a whole, using its arguments and body.
        return node

    def visit_For(self, node: nodes.For, *args, **kwargs):
        if self.dependencies.mask(node.iter) & _ITEM:
            return nodes.Output([nodes.TemplateData(_ITEM_MARK)]).set_lineno(node.lineno)
        return self.generic_visit(node, *args, **kwargs)

    def visit_FilterBlock(self, node: nodes.FilterBlock, *args, **kwargs):
        return nodes.Output([nodes.TemplateData(_ITEM_MARK)]).set_lineno(node.lineno)

    visit_CallBlock = visit_FilterBlock


def infer_show_media_directory(
    output_template: str,
    values: Mapping[str, object],
    *,
    environment: Environment,
    sanitize_component: Callable[[str], str],
    season_names: tuple[str, ...] = (),
) -> ShowMediaDirectory:
    """Return a logical /downloads path, or an explanation instead of guessing.

    The caller supplies the production sandbox, finalizer and filename policy.
    No database assignments or filesystem writes are performed by inference.
    """
    try:
        if any(marker in output_template for marker in (_ITEM_MARK, _SHOW_START, _SHOW_END)):
            raise ValueError("Output template contains unsupported control characters.")
        tree = environment.parse(output_template)
        if any(tree.find_all((nodes.Include, nodes.Import, nodes.FromImport, nodes.Extends))):
            raise ValueError("Show root cannot be inferred from an external template.")
        _trim_straight_line_filename(tree)
        dependencies = _Dependencies(tree, values, environment)
        branches = [
            node for node in tree.find_all(nodes.If)
            if dependencies.mask(node.test) & _ITEM and any(_emitted_outputs(node))
        ]
        collapse_branches = 2 ** len(branches) > _MAX_BRANCH_VARIANTS
        for index, node in enumerate(branches):
            node._show_root_branch = index

        known_seasons = {sanitize_component(name).casefold() for name in season_names if name}
        show_names = {
            sanitize_component(str(values[name]))
            for name in ("show", "show_title") if values.get(name)
        }
        candidates: list[tuple[list[str], list[bool]]] = []
        variants = [()] if collapse_branches else product((False, True), repeat=len(branches))
        for choices in variants:
            symbolic = _SymbolicOutput(dependencies, choices, collapse_branches=collapse_branches).visit(deepcopy(tree))
            template = environment.from_string(symbolic)
            rendered = template.render(dict(values))
            if not rendered.startswith("/downloads/") or "\n" in rendered or "\r" in rendered:
                raise ValueError("Every output branch must stay inside /downloads/ on a single line.")
            if len(rendered) > 8192:
                raise ValueError("Rendered output path is too long.")
            parts, identities = [], []
            # The final component is always the media filename, never the root.
            for component in rendered.split("/")[2:-1]:
                if _ITEM_MARK in component:
                    break
                show_value = any(value for value in _SHOW_VALUE.findall(component))
                plain = component.replace(_SHOW_START, "").replace(_SHOW_END, "")
                if not plain:
                    continue
                if plain in {".", ".."}:
                    raise ValueError("Show root cannot contain relative path components.")
                cleaned = sanitize_component(plain)
                identity = show_value or cleaned in show_names
                if any(identities) and not show_value and (
                    _SEASON_FOLDER.fullmatch(cleaned) or cleaned.casefold() in known_seasons
                ):
                    break
                parts.append(cleaned)
                identities.append(identity)
            candidates.append((parts, identities))

        common = candidates[0][0].copy()
        for parts, _ in candidates[1:]:
            shared_length = 0
            for left, right in zip(common, parts):
                if left != right:
                    break
                shared_length += 1
            common = common[:shared_length]
        if not common or not all(any(identities[:len(common)]) for _, identities in candidates):
            raise ValueError("No shared show-specific directory could be established. Artwork will not be written to a shared library folder.")
        return ShowMediaDirectory("/downloads/" + "/".join(common))
    except (TemplateError, TypeError, ValueError, ArithmeticError) as exc:
        return ShowMediaDirectory(None, str(exc))
