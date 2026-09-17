"""Normalize Jinja output-template expression spacing.

Revision ID: 9b1f4e7c2d6a
Revises: a4e7d18c2f90
"""
from __future__ import annotations

import re

from alembic import op
import sqlalchemy as sa


revision = "9b1f4e7c2d6a"
down_revision = "a4e7d18c2f90"
branch_labels = None
depends_on = None


_END_RAW_RE = re.compile(r"{%[-]?\s*endraw\s*[-]?%}")


def _statement_keyword(source: str) -> str:
    body = source[2:-2] if source.startswith("{%") and source.endswith("%}") else source
    match = re.match(r"\s*-?\s*([A-Za-z_][A-Za-z0-9_]*)", body)
    return match.group(1) if match else ""


def _find_tag_end(source: str, start: int, end_delimiter: str) -> int:
    if end_delimiter == "#}":
        return source.find(end_delimiter, start + 2)

    quote: str | None = None
    escaped = False
    index = start + 2
    while index < len(source) - 1:
        character = source[index]
        if quote:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
            index += 1
            continue

        if character in {"'", '"'}:
            quote = character
            index += 1
            continue

        if source.startswith(end_delimiter, index):
            return index
        index += 1
    return -1


def _next_tag(source: str, cursor: int) -> tuple[int, str, str, str] | None:
    candidates = []
    for start_delimiter, end_delimiter, tag_type in (
        ("{{", "}}", "expression"),
        ("{%", "%}", "statement"),
        ("{#", "#}", "comment"),
    ):
        index = source.find(start_delimiter, cursor)
        if index >= 0:
            candidates.append((index, start_delimiter, end_delimiter, tag_type))
    return min(candidates, default=None, key=lambda candidate: candidate[0])


def _normalize_output_template_expression_spacing(output_template: str) -> str:
    pieces: list[str] = []
    cursor = 0
    raw = False

    while cursor < len(output_template):
        if raw:
            match = _END_RAW_RE.search(output_template, cursor)
            if not match:
                pieces.append(output_template[cursor:])
                break
            pieces.append(output_template[cursor:match.end()])
            cursor = match.end()
            raw = False
            continue

        next_tag = _next_tag(output_template, cursor)
        if next_tag is None:
            pieces.append(output_template[cursor:])
            break

        start, _start_delimiter, end_delimiter, tag_type = next_tag
        pieces.append(output_template[cursor:start])
        end = _find_tag_end(output_template, start, end_delimiter)
        if end < 0:
            pieces.append(output_template[start:])
            break

        token_end = end + len(end_delimiter)
        token = output_template[start:token_end]
        if tag_type == "expression" and not (token.startswith("{{-") or token.endswith("-}}")):
            body = token[2:-2].strip()
            pieces.append(f"{{{{ {body} }}}}" if body else token)
        else:
            pieces.append(token)

        if tag_type == "statement" and _statement_keyword(token) == "raw":
            raw = True
        cursor = token_end

    return "".join(pieces)


def upgrade() -> None:
    bind = op.get_bind()
    profiles = sa.table(
        "local_media_profiles",
        sa.column("id", sa.Integer),
        sa.column("type", sa.String),
        sa.column("output_template", sa.String),
        sa.column("preferred_format", sa.String),
    )

    rows = list(bind.execute(sa.select(
        profiles.c.id,
        profiles.c.type,
        profiles.c.output_template,
        profiles.c.preferred_format,
    )).mappings())

    normalized_keys: dict[tuple[str, str, str], int] = {}
    updates: list[tuple[int, str]] = []
    for row in rows:
        normalized = _normalize_output_template_expression_spacing(row["output_template"])
        key = (row["type"], normalized, row["preferred_format"])
        existing_id = normalized_keys.get(key)
        if existing_id is not None and existing_id != row["id"]:
            raise RuntimeError(
                "Cannot normalize Local Media Profile output templates because profiles "
                f"{existing_id} and {row['id']} would become duplicates. Delete or change "
                "one of those profiles before upgrading."
            )
        normalized_keys[key] = row["id"]
        if normalized != row["output_template"]:
            updates.append((row["id"], normalized))

    for profile_id, normalized in updates:
        bind.execute(
            sa.update(profiles)
            .where(profiles.c.id == profile_id)
            .values(output_template=normalized)
        )


def downgrade() -> None:
    # Spacing normalization is semantically neutral and intentionally retained.
    pass
