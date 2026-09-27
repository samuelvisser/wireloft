"""Infer a shared show directory using the reusable Jinja output analysis."""
from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable, Mapping

from jinja2 import Environment, TemplateError, nodes

from .jinja_analysis import UnknownOutput, analyze_template, expression_dependencies
from .jinja_analysis.expressions import analysis_environment

_ITEM_MARK, _SHOW_START, _SHOW_END = "\x01", "\x02", "\x03"
_SEASON_FOLDER = re.compile(r"^(?:s(?:eason)?[\W_]?\d+|specials|extras|trailers|featurettes)$", re.I)
_SHOW_VALUE = re.compile("\x02(.*?)\x03", re.S)


@dataclass(frozen=True)
class ShowMediaDirectory:
    path: str | None
    reason: str | None = None


def _emitted_outputs(node: nodes.Node):
    if isinstance(node, (nodes.Macro, nodes.Assign, nodes.AssignBlock)):
        return
    if isinstance(node, nodes.Output):
        yield node
    for child in node.iter_child_nodes():
        yield from _emitted_outputs(child)


def _trim_straight_line_filename(tree: nodes.Template) -> None:
    """Filename-only logic cannot affect a directory; trim only a proven boundary."""
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


def infer_show_media_directory(
    output_template: str,
    values: Mapping[str, object],
    *,
    environment: Environment,
    sanitize_component: Callable[[str], str],
    season_names: tuple[str, ...] = (),
) -> ShowMediaDirectory:
    """Apply show/season directory policy to guarded symbolic Jinja output.

    Real show values are known constants; episode/season values remain symbolic.
    Markers are added only after Jinja evaluates expressions, never to filters'
    inputs. An incomplete analysis can still yield a proven directory prefix.
    """
    try:
        if any(marker in output_template for marker in (_ITEM_MARK, _SHOW_START, _SHOW_END)):
            raise ValueError("Output template contains unsupported control characters.")
        tree = environment.parse(output_template)
        if any(tree.find_all((nodes.Include, nodes.Import, nodes.FromImport, nodes.Extends))):
            raise ValueError("Show root cannot be inferred from an external template.")
        _trim_straight_line_filename(tree)
        show_fields = {name for name in values if name in {"show", "show_title"} or name.startswith("meta_show_")}
        analysis = analyze_template(tree, environment=environment, variables=values,
                                    known_values={name: values[name] for name in show_fields})
        evaluator = analysis_environment(environment)
        known_seasons = {sanitize_component(name).casefold() for name in season_names if name}
        show_names = {sanitize_component(str(values[name])) for name in ("show", "show_title") if values.get(name)}
        candidates = []
        for variant in analysis.variants:
            output = []
            for part in variant.parts:
                if isinstance(part, str):
                    output.append(part)
                elif isinstance(part, UnknownOutput):
                    output.append(_ITEM_MARK)
                else:
                    dependencies = expression_dependencies(part)
                    if dependencies - show_fields:
                        output.append(_ITEM_MARK)
                        continue
                    ast = nodes.Template([nodes.Output([part])]).set_lineno(1).set_environment(evaluator)
                    value = evaluator.from_string(ast).render()
                    output.append(_SHOW_START + value + _SHOW_END if dependencies & show_fields else value)
            rendered = "".join(output)
            if not rendered.startswith("/downloads/") or "\n" in rendered or "\r" in rendered:
                raise ValueError("Every output branch must stay inside /downloads/ on a single line.")
            if len(rendered) > 8192:
                raise ValueError("Rendered output path is too long.")
            parts, identities = [], []
            for component in rendered.split("/")[2:-1]:
                if _ITEM_MARK in component:
                    break
                show_value = any(_SHOW_VALUE.findall(component))
                plain = component.replace(_SHOW_START, "").replace(_SHOW_END, "")
                if not plain:
                    continue
                if plain in {".", ".."}:
                    raise ValueError("Show root cannot contain relative path components.")
                cleaned = sanitize_component(plain)
                if any(identities) and not show_value and (
                    _SEASON_FOLDER.fullmatch(cleaned) or cleaned.casefold() in known_seasons
                ):
                    break
                parts.append(cleaned)
                identities.append(show_value or cleaned in show_names)
            candidates.append((parts, identities))
        if not candidates:
            raise ValueError(analysis.reason or "No reachable output path could be established.")
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
