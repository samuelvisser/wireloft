from __future__ import annotations

import pytest
from sqlalchemy import column, select
from sqlalchemy.dialects import sqlite

from backend.api.pagination import (
    InvalidCursorError,
    KeysetField,
    cursor_key_values,
    decode_cursor,
    encode_cursor,
    keyset_after,
)


def test_cursor_round_trip_is_url_safe_and_opaque():
    values = {
        "kind": "example",
        "id": 42,
        "key": ["alpha", 7],
    }

    cursor = encode_cursor(values)

    assert "=" not in cursor
    assert decode_cursor(cursor) == values


def test_invalid_cursor_is_rejected():
    with pytest.raises(InvalidCursorError):
        decode_cursor("not-a-valid-cursor")


def test_keyset_after_builds_lexicographic_predicate():
    first = column("first")
    second = column("second")
    stmt = select(first, second).where(keyset_after([
        KeysetField(first, 10),
        KeysetField(second, 5, descending=True),
    ]))

    sql = str(stmt.compile(
        dialect=sqlite.dialect(),
        compile_kwargs={"literal_binds": True},
    ))

    assert "first > 10" in sql
    assert "first = 10" in sql
    assert "second < 5" in sql



def test_cursor_key_values_reject_nested_or_boolean_values():
    with pytest.raises(InvalidCursorError):
        cursor_key_values({"key": ["valid", {"nested": True}]}, length=2)

    with pytest.raises(InvalidCursorError):
        cursor_key_values({"key": [True]}, length=1)
