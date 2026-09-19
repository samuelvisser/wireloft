from __future__ import annotations

from sqlalchemy import case, func, literal, or_


def _escape_like(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("%", "\\%")
        .replace("_", "\\_")
    )


def search_all_terms(search: str | None, *columns):
    """Require every whitespace-separated search term to match at least one column."""
    terms = (search or "").strip().split()
    filters = []
    for term in terms:
        pattern = f"%{_escape_like(term)}%"
        filters.append(or_(*(column.ilike(pattern, escape="\\") for column in columns)))
    return filters


def search_relevance_score(search: str | None, *columns):
    """Score likely search candidates, preferring phrase matches in earlier columns.

    The score is intended only for ordering an already-filtered query. A complete
    phrase match dominates token-level matches, while earlier columns are treated
    as more important so callers can put the item's own title before parent or
    secondary metadata.
    """
    phrase = (search or "").strip().lower()
    if not phrase:
        return None

    terms = phrase.split()
    phrase_escaped = _escape_like(phrase)
    score = literal(0)

    for index, column in enumerate(columns):
        # Keep weights comparable between queries with different numbers of
        # searchable columns (for example movies versus movie extras).
        weight = max(1, 8 - index)
        normalized = func.lower(func.coalesce(column, ""))

        score += case(
            (normalized == phrase, 400 * weight),
            (normalized.like(f"{phrase_escaped}%", escape="\\"), 250 * weight),
            (normalized.like(f"%{phrase_escaped}%", escape="\\"), 150 * weight),
            else_=0,
        )

        for term in terms:
            term_escaped = _escape_like(term)
            score += case(
                (normalized == term, 40 * weight),
                (normalized.like(f"{term_escaped}%", escape="\\"), 25 * weight),
                (normalized.like(f"%{term_escaped}%", escape="\\"), 10 * weight),
                else_=0,
            )

    return score
