from __future__ import annotations

from unittest.mock import Mock

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session


def test_event_is_emitted_only_after_commit(monkeypatch):
    from task_manager.events import transactional

    emit = Mock()
    monkeypatch.setattr(transactional, "emit_event", emit)
    session = Session(create_engine("sqlite+pysqlite:///:memory:"))

    session.execute(text("SELECT 1"))
    transactional.queue_event(session, "show.added", {"resource_id": 42})
    assert emit.call_count == 0

    session.commit()
    emit.assert_called_once_with("show.added", {"resource_id": 42})
    session.close()


def test_event_is_discarded_on_rollback(monkeypatch):
    from task_manager.events import transactional

    emit = Mock()
    monkeypatch.setattr(transactional, "emit_event", emit)
    session = Session(create_engine("sqlite+pysqlite:///:memory:"))

    session.execute(text("SELECT 1"))
    transactional.queue_event(session, "show.added", {"resource_id": 42})
    session.rollback()
    session.commit()

    emit.assert_not_called()
    session.close()
