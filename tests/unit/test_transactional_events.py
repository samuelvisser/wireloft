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


def test_committed_event_batch_adapter_derives_one_event_from_full_batch(monkeypatch):
    from task_manager.events import transactional

    emit = Mock()
    monkeypatch.setattr(transactional, "emit_event", emit)
    monkeypatch.setattr(transactional, "_COMMITTED_EVENT_BATCH_ADAPTERS", {})
    session = Session(create_engine("sqlite+pysqlite:///:memory:"))

    @transactional.committed_event_batch_adapter("test.transactional.batch")
    def derive(events):
        assert [event.name for event in events] == [
            "episode.published_final",
            "show.indexed",
        ]
        return (
            transactional.PendingEvent(
                "worker.run_requested",
                {"resource_type": "show", "resource_id": 12},
            ),
        )

    try:
        transactional.queue_event(
            session,
            "episode.published_final",
            {"resource_id": 501, "show_id": 12},
        )
        transactional.queue_event(
            session,
            "show.indexed",
            {"resource_id": 12},
        )
        session.commit()

        assert [item.args for item in emit.call_args_list] == [
            ("episode.published_final", {"resource_id": 501, "show_id": 12}),
            ("show.indexed", {"resource_id": 12}),
            ("worker.run_requested", {"resource_type": "show", "resource_id": 12}),
        ]
    finally:
        transactional.unregister_committed_event_batch_adapter("test.transactional.batch")
        session.close()
