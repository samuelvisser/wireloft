from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import Mock


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

    # Reproduce the monitor ordering: fresh Daily Wire state has already moved the
    # row to final before identifier reconciliation, while the captured old status
    # still says LIVE. This is the initial publication, not a post-publication edit.
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

    # Remember that the row was published, then simulate Daily Wire temporarily
    # regressing it to processing before another identifier correction.
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


def test_download_profile_worker_subscribes_to_identifier_changes():
    from task_manager.tasks.helpers.episodes.events import EPISODE_IDENTIFIER_CHANGED_EVENT
    from task_manager.tasks.workers.download_profile_worker import download_profile_worker
    from task_manager.tasks.workers.redownload_show_episodes_worker import redownload_show_episodes_worker

    event_names = {
        trigger.event_name
        for trigger in download_profile_worker._task_meta.triggers
        if trigger.trigger_type == "event"
    }
    assert EPISODE_IDENTIFIER_CHANGED_EVENT in event_names
    assert "episode" in redownload_show_episodes_worker._task_meta.allowed_resource_types


def test_identifier_change_redownloads_only_affected_profile_paths(monkeypatch):
    from task_manager.tasks.workers.download_profile_worker import identifier_changes

    episode, _ = _fake_episode(status="published_final", identifier="ep.2500")

    def local_profile(profile_id: int, template: str):
        return SimpleNamespace(id=profile_id, output_template=template)

    shared_lmp = local_profile(10, "/downloads/{show}/{episode_identifier}.ext")
    profiles = [
        SimpleNamespace(id=1, local_media_profile_id=10, local_media_profile=shared_lmp),
        SimpleNamespace(
            id=2,
            local_media_profile_id=11,
            local_media_profile=local_profile(11, "/downloads/{{ show }}/{{ episode_label }}.ext"),
        ),
        SimpleNamespace(
            id=3,
            local_media_profile_id=12,
            local_media_profile=local_profile(12, "/downloads/{show}/{episode_title}.ext"),
        ),
        SimpleNamespace(
            id=4,
            local_media_profile_id=13,
            local_media_profile=local_profile(13, "/downloads/{show}/{episode_identifier}.ext"),
        ),
        # A second Download Profile sharing the first Local Media Profile points at
        # the same artifact/path and must not schedule a second destructive job.
        SimpleNamespace(id=5, local_media_profile_id=10, local_media_profile=shared_lmp),
    ]

    class FakeSession:
        def __init__(self):
            self.rollbacks = 0

        def get(self, _model, resource_id):
            return episode if resource_id == episode.id else None

        def rollback(self):
            self.rollbacks += 1

    session = FakeSession()
    triggered = Mock()
    monkeypatch.setattr(
        identifier_changes,
        "resolve_target_profiles",
        lambda *_args, **_kwargs: profiles,
    )
    monkeypatch.setattr(
        identifier_changes,
        "get_download_profile_episodes",
        lambda _session, profile, *, only_episode: (
            [] if profile.id == 4 else [only_episode]
        ),
    )
    monkeypatch.setattr(identifier_changes, "trigger_now", triggered)

    count = identifier_changes.handle_episode_identifier_changed(
        session,
        episode_id=episode.id,
        old_episode_identifier="ep-extra.2500.1",
        new_episode_identifier=episode.episode_identifier,
    )

    assert count == 2
    assert session.rollbacks == 1
    assert [call.kwargs["download_profile_id"] for call in triggered.call_args_list] == [1, 2]
    for call in triggered.call_args_list:
        assert call.kwargs["def_key"] == "redownload_show_episodes_worker"
        assert call.kwargs["resource_type"] == "episode"
        assert call.kwargs["resource_id"] == episode.id
        assert call.kwargs["max_retries"] == 0


def test_redownload_worker_can_target_one_episode(monkeypatch):
    from backend.db.models import Episode
    from task_manager.tasks.workers.redownload_show_episodes_worker import service

    show = SimpleNamespace(id=7, slug="test-show", title="Test Show")
    episode = SimpleNamespace(
        id=42,
        slug="test-episode",
        title="Test Episode",
        show=show,
    )
    profile = SimpleNamespace(id=9)
    prepared_inputs: list[list[tuple[object, object]]] = []

    class FakeSession:
        def get(self, model, resource_id):
            if model is Episode and resource_id == episode.id:
                return episode
            return None

        def rollback(self):
            pass

        def expire_all(self):
            pass

    async def no_sleep(_seconds):
        return None

    monkeypatch.setattr(service.asyncio, "sleep", no_sleep)
    monkeypatch.setattr(
        service,
        "_selected_profiles",
        lambda *_args, **_kwargs: [profile],
    )
    monkeypatch.setattr(
        service,
        "get_download_profile_episodes",
        lambda _session, candidate_profile, *, only_episode: (
            [only_episode] if candidate_profile is profile else []
        ),
    )

    def prepare(_session, targets):
        prepared_inputs.append(list(targets))
        return [SimpleNamespace(operation_id="operation-1")]

    monkeypatch.setattr(service, "_prepare_redownloads", prepare)
    monkeypatch.setattr(service, "_check_targets", lambda *_args: (1, 100, None))

    result = asyncio.run(
        service.run_redownload_show_episodes_worker(
            FakeSession(),
            episode_id=episode.id,
            download_profile_id=profile.id,
        )
    )

    assert prepared_inputs == [[(episode, profile)]]
    assert result["episode_id"] == episode.id
    assert result["episode_files"] == 1
    assert result["download_profiles"] == 1
