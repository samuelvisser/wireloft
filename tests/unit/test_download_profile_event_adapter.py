from __future__ import annotations


def _event(name: str, **data):
    from task_manager.events.transactional import PendingEvent

    return PendingEvent(name, data)


def _adapt(*events):
    from task_manager.tasks.workers.download_profile_worker.event_adapter import (
        adapt_download_profile_events,
    )

    return [
        (event.name, event.data)
        for event in adapt_download_profile_events(tuple(events))
    ]


def test_published_episode_added_requests_episode_scope():
    assert _adapt(
        _event(
            "episode.added",
            resource_id=501,
            show_id=12,
            status="published_final",
        ),
    ) == [
        (
            "download_profile.run_requested",
            {"resource_type": "episode", "resource_id": 501},
        ),
    ]


def test_non_published_episode_added_does_not_request_download_profile_run():
    assert _adapt(
        _event(
            "episode.added",
            resource_id=501,
            show_id=12,
            status="scheduled",
        ),
    ) == []



def test_published_status_update_requests_episode_scope_without_worker_specific_event():
    assert _adapt(
        _event(
            "episode.status_updated",
            resource_id=501,
            show_id=12,
            status="published_with_countdown",
        ),
    ) == [
        (
            "download_profile.run_requested",
            {"resource_type": "episode", "resource_id": 501},
        ),
    ]

def test_show_scope_subsumes_new_episode_events_from_same_index_transaction():
    assert _adapt(
        _event(
            "episode.added",
            resource_id=501,
            show_id=12,
            status="published_final",
        ),
        _event(
            "episode.status_updated",
            resource_id=501,
            show_id=12,
            status="published_final",
        ),
        _event(
            "episode.published_final",
            resource_id=501,
            show_id=12,
        ),
        _event(
            "show.indexed",
            resource_id=12,
            indexed_count=1,
        ),
    ) == [
        (
            "download_profile.run_requested",
            {"resource_type": "show", "resource_id": 12},
        ),
    ]


def test_profile_events_collapse_to_one_profile_scope():
    assert _adapt(
        _event(
            "download_profile.added",
            resource_id=91,
            show_id=12,
        ),
        _event(
            "download_profile.updated",
            resource_id=91,
            show_id=12,
        ),
    ) == [
        (
            "download_profile.run_requested",
            {"resource_type": "download_profile", "resource_id": 91},
        ),
    ]


def test_show_scope_subsumes_profile_and_episode_scopes_for_same_show_only():
    assert _adapt(
        _event(
            "download_profile.updated",
            resource_id=91,
            show_id=12,
        ),
        _event(
            "episode.published_with_countdown",
            resource_id=501,
            show_id=12,
        ),
        _event(
            "episode.published_final",
            resource_id=777,
            show_id=99,
        ),
        _event(
            "show.indexed",
            resource_id=12,
        ),
    ) == [
        (
            "download_profile.run_requested",
            {"resource_type": "episode", "resource_id": 777},
        ),
        (
            "download_profile.run_requested",
            {"resource_type": "show", "resource_id": 12},
        ),
    ]



def test_index_transaction_emits_one_show_scoped_worker_request(monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session
    from task_manager.events import transactional
    from task_manager.tasks.workers.download_profile_worker.event_adapter import (
        DOWNLOAD_PROFILE_RUN_REQUESTED_EVENT,
    )

    emitted = []
    monkeypatch.setattr(
        transactional,
        "emit_event",
        lambda name, data: emitted.append((name, data)),
    )
    session = Session(create_engine("sqlite+pysqlite:///:memory:"))
    try:
        transactional.queue_event(
            session,
            "episode.added",
            {
                "resource_id": 501,
                "show_id": 12,
                "status": "published_final",
            },
        )
        transactional.queue_event(
            session,
            "episode.status_updated",
            {
                "resource_id": 501,
                "show_id": 12,
                "status": "published_final",
            },
        )
        transactional.queue_event(
            session,
            "episode.published_final",
            {"resource_id": 501, "show_id": 12},
        )
        transactional.queue_event(
            session,
            "show.indexed",
            {"resource_id": 12, "indexed_count": 1},
        )
        session.commit()
    finally:
        session.close()

    assert [
        data
        for name, data in emitted
        if name == DOWNLOAD_PROFILE_RUN_REQUESTED_EVENT
    ] == [
        {"resource_type": "show", "resource_id": 12},
    ]
