from __future__ import annotations

from contextlib import contextmanager

from backend.db import get_session


@contextmanager
def db_session():
    """Context manager for database sessions."""
    s = get_session()
    try:
        yield s
    finally:
        s.close()
