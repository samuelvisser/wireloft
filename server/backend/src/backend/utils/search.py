from __future__ import annotations

from sqlalchemy import or_


def search_all_terms(search: str | None, *columns):
    """Require every whitespace-separated search term to match at least one column."""
    terms = (search or "").strip().split()
    filters = []
    for term in terms:
        escaped = (
            term.replace("\\", "\\\\")
            .replace("%", "\\%")
            .replace("_", "\\_")
        )
        pattern = f"%{escaped}%"
        filters.append(or_(*(column.ilike(pattern, escape="\\") for column in columns)))
    return filters
