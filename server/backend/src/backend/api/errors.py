# errors.py
import re
from typing import List, cast
from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError

def _columns_from_constraint_name(name: str) -> List[str]:
    # Expects patterns like "uq_<table>_<col>" or "uq_<table>_<col0>_<col1>"
    # Adjust if you encode multiple columns in the naming_convention.
    if not name:
        return []
    if name.startswith("uq_"):
        parts = name.split("_")
        # uq, <table>, <col> or more cols
        return parts[2:] if len(parts) >= 3 else []
    return []

def _try_extract_mysql_duplicate_key(err: Exception) -> List[str]:
    # MySQL/MariaDB (errcode 1062) emits messages like:
    # "Duplicate entry 'foo' for key 'uq_items_name'"
    m = re.search(r"for key '([^']+)'", str(err))
    if m:
        return _columns_from_constraint_name(m.group(1))
    return []

def _try_extract_sqlite_unique(err: Exception) -> List[str]:
    # SQLite emits messages like:
    # "UNIQUE constraint failed: items.name"
    m = re.search(r"UNIQUE constraint failed: ([\w]+)\.([\w]+)", str(err))
    if m:
        return [m.group(2)]
    return []

def _extract_columns_from_integrity_error(exc: IntegrityError) -> List[str]:
    # Postgres (psycopg2 / psycopg) gives constraint name directly:
    # exc.orig.diag.constraint_name
    diag = getattr(exc.orig, "diag", None)
    if diag is not None:
        name = getattr(diag, "constraint_name", None)
        cols = _columns_from_constraint_name(name)
        if cols:
            return cols

    # MySQL / MariaDB
    cols = _try_extract_mysql_duplicate_key(exc.orig)
    if cols:
        return cols

    # SQLite
    cols = _try_extract_sqlite_unique(exc.orig)
    if cols:
        return cols

    return []

async def integrity_error_handler(request: Request, exc: Exception) -> JSONResponse:
    err = cast(IntegrityError, exc)

    # You may want to roll back here if you manage session manually per request
    cols = _extract_columns_from_integrity_error(err)
    if not cols:
        # generic, non-field-specific unique violation (or other integrity issue)
        return JSONResponse(
            status_code=409,
            content={
                "detail": [
                    {
                        "loc": ["body", "__all__"],
                        "msg": "Integrity constraint violated",
                        "type": "integrity_error"
                    }
                ]
            },
        )

    return JSONResponse(
        status_code=409,
        content={
            "detail": [
                {
                    "loc": ["body", col],
                    "msg": "Already in use",
                    "type": "unique_violation"
                } for col in cols
            ]
        },
    )
