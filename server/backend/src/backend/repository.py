from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Generic, Iterable, List, Optional, Sequence, Tuple, Type, TypeVar
import sqlite3

from pydantic import BaseModel


T = TypeVar("T", bound=BaseModel)


@dataclass(frozen=True)
class OrderBy:
    """Simple order-by descriptor.

    Example: OrderBy("created_date", descending=True)
    """

    column: str
    descending: bool = False

    def to_sql(self) -> str:
        return f"{self.column} {'DESC' if self.descending else 'ASC'}"


class SqlModelRepository(Generic[T]):
    """Generic, minimal repository that maps SQLite rows to Pydantic models.

    Goals:
    - Always uses SELECT * so adding a new DB column and a matching Pydantic field requires no query changes.
    - Validates and returns Pydantic models (v2), relying on Pydantic for type coercion where appropriate.
    - Protects against SQL injection by validating column names via PRAGMA table_info.

    Usage:
        from .db import connect_db
        from .records.MediaProfileRecord import MediaProfileRecord

        conn = connect_db()
        repo = SqlModelRepository(conn, MediaProfileRecord, table="media_profiles")
        profiles: list[MediaProfileRecord] = repo.all(order_by=[OrderBy("id")])
        first: MediaProfileRecord | None = repo.get(1)
    """

    def __init__(self, conn: sqlite3.Connection, model: Type[T], table: str, id_column: str = "id") -> None:
        self._conn = conn
        self._model = model
        self._table = table
        self._id_col = id_column
        self._columns_cache: Optional[Tuple[str, ...]] = None

    # --------------- Public API ---------------
    def all(
        self,
        *,
        order_by: Optional[Sequence[OrderBy]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[T]:
        sql, params = self._build_select(order_by=order_by, limit=limit, offset=offset)
        rows = self._execute(sql, params)
        return [self._to_model(r) for r in rows]

    def get(self, id_value: Any) -> Optional[T]:
        sql, params = self._build_select(where={self._id_col: id_value}, limit=1)
        rows = self._execute(sql, params)
        if not rows:
            return None
        return self._to_model(rows[0])

    def find(
        self,
        where: Optional[Dict[str, Any]] = None,
        *,
        order_by: Optional[Sequence[OrderBy]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> List[T]:
        sql, params = self._build_select(where=where, order_by=order_by, limit=limit, offset=offset)
        rows = self._execute(sql, params)
        return [self._to_model(r) for r in rows]

    def one(self, where: Dict[str, Any]) -> Optional[T]:
        sql, params = self._build_select(where=where, limit=1)
        rows = self._execute(sql, params)
        if not rows:
            return None
        return self._to_model(rows[0])

    # --------------- Internals ---------------
    def _table_columns(self) -> Tuple[str, ...]:
        if self._columns_cache is not None:
            return self._columns_cache
        cur = self._conn.cursor()
        cur.execute(f"PRAGMA table_info({self._table});")
        cols = tuple(row[1] for row in cur.fetchall())  # row: (cid, name, type, ...)
        self._columns_cache = cols
        return cols

    def _validate_columns(self, cols: Iterable[str]) -> Tuple[str, ...]:
        valid = set(self._table_columns())
        bad = [c for c in cols if c not in valid]
        if bad:
            raise ValueError(f"Unknown column(s) for table '{self._table}': {', '.join(bad)}")
        return tuple(cols)

    def _build_select(
        self,
        *,
        where: Optional[Dict[str, Any]] = None,
        order_by: Optional[Sequence[OrderBy]] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
    ) -> Tuple[str, Tuple[Any, ...]]:
        sql = [f"SELECT * FROM {self._table}"]
        params: List[Any] = []

        if where:
            self._validate_columns(where.keys())
            clauses = [f"{col} = ?" for col in where]
            sql.append("WHERE " + " AND ".join(clauses))
            params.extend(where.values())

        if order_by:
            # Validate order-by columns too
            self._validate_columns(ob.column for ob in order_by)
            sql.append("ORDER BY " + ", ".join(ob.to_sql() for ob in order_by))

        if limit is not None:
            if not isinstance(limit, int) or limit < 0:
                raise ValueError("limit must be a non-negative int or None")
            sql.append("LIMIT ?")
            params.append(limit)
        if offset is not None:
            if not isinstance(offset, int) or offset < 0:
                raise ValueError("offset must be a non-negative int or None")
            sql.append("OFFSET ?")
            params.append(offset)

        return " ".join(sql), tuple(params)

    def _execute(self, sql: str, params: Tuple[Any, ...]) -> List[sqlite3.Row]:
        cur = self._conn.cursor()
        cur.execute(sql, params)
        return list(cur.fetchall())

    def _to_model(self, row: sqlite3.Row) -> T:
        # Convert sqlite3.Row to plain dict to pass into Pydantic.
        payload = {k: row[k] for k in row.keys()}
        # Let Pydantic handle type coercion and validation.
        return self._model.model_validate(payload)
