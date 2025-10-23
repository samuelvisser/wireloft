from contextlib import contextmanager
from backend.db import get_session


@contextmanager
def db_session():
    s = get_session()
    try:
        yield s
    finally:
        s.close()