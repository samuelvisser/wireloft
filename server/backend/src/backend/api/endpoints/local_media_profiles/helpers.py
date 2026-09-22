from __future__ import annotations

from copy import deepcopy

from fastapi import HTTPException
from jinja2 import nodes
from jinja2.visitor import NodeTransformer
from sqlalchemy.orm import Session

from backend.api.models.local_media_profile import LocalMediaProfileAPIBaseIn
from backend.db.models import LocalMediaProfileBase
from backend.types.local_media_profile_types import PreferredFormat
from backend.utils.output_template import _parse_output_template, replace_output_extension


class _NonComparableTemplate(Exception):
    pass


def _normalize_expression(node: nodes.Expr, environment: dict[str, nodes.Expr]) -> nodes.Expr:
    class NormalizeNames(NodeTransformer):
        def visit_Name(self, name: nodes.Name, *args, **kwargs):
            replacement = environment.get(name.name)
            return deepcopy(replacement) if name.ctx == "load" and replacement is not None else name

    return NormalizeNames().visit(deepcopy(node))


def _canonical_expression(node: nodes.Expr, environment: dict[str, nodes.Expr]) -> str:
    node = _normalize_expression(node, environment)
    if isinstance(node, nodes.TemplateData):
        return node.data
    if isinstance(node, nodes.Name):
        return f"{{{node.name}}}"
    if isinstance(node, nodes.Const):
        return str(node.value)
    return repr(node)


def _canonical_body(
    statements: list[nodes.Stmt],
    states: list[tuple[str, dict[str, nodes.Expr]]],
) -> list[tuple[str, dict[str, nodes.Expr]]]:
    for statement in statements:
        next_states = []
        for text, environment in states:
            if isinstance(statement, nodes.Output):
                next_states.append((
                    text + "".join(
                        _canonical_expression(node, environment)
                        for node in statement.nodes
                    ),
                    environment,
                ))
            elif isinstance(statement, nodes.Assign):
                if not isinstance(statement.target, nodes.Name):
                    raise _NonComparableTemplate
                updated = dict(environment)
                updated[statement.target.name] = _normalize_expression(
                    statement.node,
                    environment,
                )
                next_states.append((text, updated))
            elif isinstance(statement, nodes.AssignBlock):
                if not isinstance(statement.target, nodes.Name) or statement.filter is not None:
                    raise _NonComparableTemplate
                for captured, _captured_environment in _canonical_body(
                    statement.body,
                    [("", dict(environment))],
                ):
                    updated = dict(environment)
                    updated[statement.target.name] = nodes.Const(captured)
                    next_states.append((text, updated))
            elif isinstance(statement, nodes.If):
                for branch in [
                    statement.body,
                    *[elif_node.body for elif_node in statement.elif_],
                    statement.else_,
                ]:
                    next_states.extend(
                        _canonical_body(branch, [(text, dict(environment))])
                    )
            else:
                raise _NonComparableTemplate
        states = next_states
    return states


def _canonical_template_patterns(output_template: str) -> frozenset[str] | None:
    """Return possible symbolic outputs after removing non-output-affecting Jinja."""
    try:
        states = _canonical_body(_parse_output_template(output_template).body, [("", {})])
    except (ValueError, _NonComparableTemplate):
        return None
    return frozenset(output for output, _environment in states)


def _profile_output_patterns(
    output_template: str,
    preferred_format: PreferredFormat | str,
) -> frozenset[str] | None:
    patterns = _canonical_template_patterns(output_template)
    if patterns is None:
        return None
    extension = "m4a" if preferred_format == PreferredFormat.FORMAT_AUDIO_ONLY else "mp4"
    return frozenset(replace_output_extension(pattern, extension) for pattern in patterns)


def ensure_unique_profile_settings(
    s: Session,
    profile_model: type[LocalMediaProfileBase],
    body: LocalMediaProfileAPIBaseIn,
    *,
    exclude_id: int | None = None,
) -> None:
    query = s.query(profile_model)
    if exclude_id is not None:
        query = query.filter(LocalMediaProfileBase.id != exclude_id)

    candidate_patterns = _profile_output_patterns(
        body.output_template,
        body.preferred_format,
    )
    for existing in query.all():
        if (
            existing.output_template == body.output_template
            and existing.preferred_format == body.preferred_format
        ):
            raise HTTPException(
                status_code=409,
                detail=[{
                    "loc": ["body", "outputTemplate"],
                    "msg": "A Local Media Profile with this output path template and preferred format already exists",
                    "type": "unique_violation",
                }],
            )

        existing_patterns = _profile_output_patterns(
            existing.output_template,
            existing.preferred_format,
        )
        if (
            candidate_patterns is not None
            and existing_patterns is not None
            and candidate_patterns & existing_patterns
        ):
            raise HTTPException(
                status_code=409,
                detail=[{
                    "loc": ["body", "outputTemplate"],
                    "msg": (
                        "Output template can produce the same file as Local Media Profile "
                        f"'{existing.name}'. Choose a different output path."
                    ),
                    "type": "output_path_collision",
                }],
            )
