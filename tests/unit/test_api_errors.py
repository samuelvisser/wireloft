from __future__ import annotations

import asyncio
import json
import sqlite3

from sqlalchemy.exc import IntegrityError


def test_integrity_error_handler_serializes_generic_database_error() -> None:
    from backend.api.errors import integrity_error_handler

    exc = IntegrityError(
        "DELETE FROM local_media_profiles WHERE id = ?",
        {"id": 1},
        sqlite3.IntegrityError("FOREIGN KEY constraint failed"),
    )

    response = asyncio.run(integrity_error_handler(None, exc))  # type: ignore[arg-type]
    payload = json.loads(response.body)

    assert response.status_code == 409
    assert payload["detail"][0]["type"] == "integrity_error"
    assert payload["detail"][0]["msg"] == "FOREIGN KEY constraint failed"
