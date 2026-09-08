from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock


def _fake_episode(*, status: str, identifier: str = "ep-extra.2500.1"):
    metadata: dict[str, str | None] = {}
    show = SimpleNamespace(id=7, slug="test-show")
    episode = SimpleNamespace(
        id=42,
        slug="test-episode",
        show_id=show.id,
        show=show,
        season_id=3,
        index=2500,
        episode_identifier=identifier,
        publish_status=status,
    )
    episode.get_meta = lambda key: metadata.get(key)
    episode.set_meta = lambda key, value: metadata.__setitem__(key, value)
    return episode, metadata


def test_identifier_change_event_only_fires_after_initial_publication(monkeypatch):
    from backend.types.episode_types import EpisodePublishStatus
    from task_manager.tasks.helpers.episodes import events, identifier_reconciliation

    episode, metadata = _fake_episode(status=EpisodePublishStatus.LIVE.value)
    queued = Mock()
    target_identifier = "ep.2500"

    def fake_reconcile(_session, item, _dw_episode):
        item.episode_identifier = target_identifier
        return True

    monkeypatch.setattr(events, "queue_event", queued)
    monkeypatch.setattr(
        identifier_reconciliation,
        "reconcile_episode_identifier_from_dailywire",
        fake_reconcile,
    )

    episode.publish_status = EpisodePublishStatus.PUBLISHED_FINAL.value
    assert identifier_reconciliation.reconcile_episode_identifier(
        object(),
        episode,
        object(),
        previous_publish_status=EpisodePublishStatus.LIVE.value,
    ) is True
    assert not any(
        call.args[1] == events.EPISODE_IDENTIFIER_CHANGED_EVENT
        for call in queued.call_args_list
    )

    episode.episode_identifier = "ep-extra.2500.1"
    episode.publish_status = EpisodePublishStatus.DW_PROCESSING.value
    events.queue_episode_status_events(
        object(),
        episode=episode,
        show=episode.show,
        old_status=EpisodePublishStatus.PUBLISHED_FINAL.value,
        new_status=EpisodePublishStatus.DW_PROCESSING,
        was_created=False,
    )
    assert metadata["ep_status.was_published"] == "1"

    queued.reset_mock()
    assert identifier_reconciliation.reconcile_episode_identifier(
        object(),
        episode,
        object(),
        previous_publish_status=EpisodePublishStatus.DW_PROCESSING.value,
    ) is True

    matching = [
        call
        for call in queued.call_args_list
        if call.args[1] == events.EPISODE_IDENTIFIER_CHANGED_EVENT
    ]
    assert len(matching) == 1
    payload = matching[0].args[2]
    assert payload["resource_id"] == episode.id
    assert payload["old_episode_identifier"] == "ep-extra.2500.1"
    assert payload["new_episode_identifier"] == "ep.2500"


def test_identifier_change_is_handled_by_rename_worker():
    from task_manager.tasks.helpers.episodes.events import EPISODE_IDENTIFIER_CHANGED_EVENT
    from task_manager.tasks.workers.download_profile_worker import download_profile_worker
    from task_manager.tasks.workers.rename_file_worker import rename_file_worker

    regular_event_names = {
        trigger.event_name
        for trigger in download_profile_worker._task_meta.triggers
        if trigger.trigger_type == "event"
    }
    rename_event_names = {
        trigger.event_name
        for trigger in rename_file_worker._task_meta.triggers
        if trigger.trigger_type == "event"
    }

    assert EPISODE_IDENTIFIER_CHANGED_EVENT not in regular_event_names
    assert rename_event_names == {EPISODE_IDENTIFIER_CHANGED_EVENT}
    assert rename_file_worker._task_meta.allowed_resource_types == ("episode",)
    assert rename_file_worker._task_meta.default_max_retries == 2


def test_identifier_change_event_limits_rename_to_identifier_fields(monkeypatch):
    from task_manager.tasks.workers.rename_file_worker import entrypoint

    session = object()
    run = AsyncMock()

    class SessionContext:
        def __enter__(self):
            return session

        def __exit__(self, exc_type, exc_value, traceback):
            return False

    monkeypatch.setattr(entrypoint, "db_session", SessionContext)
    monkeypatch.setattr(entrypoint, "run_rename_file_worker", run)

    asyncio.run(entrypoint.rename_file_worker(
        resource_id=42,
        old_episode_identifier="ep-extra.2500.1",
        new_episode_identifier="ep.2500",
    ))

    run.assert_awaited_once_with(
        session,
        episode_id=42,
        local_media_profile_id=None,
        identifier_fields_only=True,
        progress=None,
    )
