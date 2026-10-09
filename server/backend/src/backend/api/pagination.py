from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy import and_, or_
from sqlalchemy.sql.elements import ColumnElement


_CURSOR_VERSION = 1


class InvalidCursorError(ValueError):
    """Raised when an opaque pagination cursor cannot be decoded safely."""


def encode_cursor(values: dict[str, Any]) -> str:
    """Encode JSON-compatible cursor state as an opaque URL-safe token."""
    payload = json.dumps(
        {"v": _CURSOR_VERSION, "values": values},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> dict[str, Any]:
    """Decode one opaque cursor and reject malformed/unknown versions."""
    try:
        padding = "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode((cursor + padding).encode("ascii"))
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeError, json.JSONDecodeError, binascii.Error) as exc:
        raise InvalidCursorError("Invalid pagination cursor") from exc

    if (
        not isinstance(payload, dict)
        or payload.get("v") != _CURSOR_VERSION
        or not isinstance(payload.get("values"), dict)
    ):
        raise InvalidCursorError("Invalid pagination cursor")
    return payload["values"]



def cursor_key_values(
        payload: dict[str, Any],
        *,
        length: int,
        allow_none: bool = False,
) -> list[str | int | float | None]:
    """Validate one decoded keyset key before binding its values into SQL."""
    raw = payload.get("key")
    if not isinstance(raw, list) or len(raw) != length:
        raise InvalidCursorError("Invalid pagination cursor key")

    values: list[str | int | float | None] = []
    for value in raw:
        if value is None and allow_none:
            values.append(value)
            continue
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise InvalidCursorError("Invalid pagination cursor key")
        values.append(value)
    return values


@dataclass(frozen=True)
class KeysetField:
    """One non-null ordered SQL value used to continue a keyset page."""

    expression: ColumnElement[Any]
    value: Any
    descending: bool = False


def keyset_after(fields: list[KeysetField]) -> ColumnElement[bool]:
    """Build a lexicographic SQL predicate for rows strictly after a cursor."""
    clauses: list[ColumnElement[bool]] = []
    equal_prefix: list[ColumnElement[bool]] = []
    for field in fields:
        comparison = (
            field.expression < field.value
            if field.descending
            else field.expression > field.value
        )
        clauses.append(and_(*equal_prefix, comparison))
        equal_prefix.append(field.expression == field.value)
    if not clauses:
        raise ValueError("At least one keyset field is required")
    return or_(*clauses)
