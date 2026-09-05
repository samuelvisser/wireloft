from __future__ import annotations

import importlib
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.mark.parametrize(
    ("module_name", "endpoint_name", "service_name", "is_update"),
    [
        (
            "backend.api.endpoints.podcast_download_profiles.router",
            "podcast_download_profiles_create",
            "create_download_profile_podcast",
            False,
        ),
        (
            "backend.api.endpoints.podcast_download_profiles.router",
            "podcast_download_profiles_update",
            "update_download_profile_podcast",
            True,
        ),
        (
            "backend.api.endpoints.series_download_profiles.router",
            "series_download_profiles_create",
            "create_download_profile_series",
            False,
        ),
        (
            "backend.api.endpoints.series_download_profiles.router",
            "series_download_profiles_update",
            "update_download_profile_series",
            True,
        ),
    ],
)
def test_direct_download_profile_writes_trigger_exact_profile_after_commit(
        monkeypatch,
        module_name,
        endpoint_name,
        service_name,
        is_update,
):
    module = importlib.import_module(module_name)
    profile = SimpleNamespace(id=73)

    class FakeSession:
        committed = False
        exited = False
        rolled_back = False

        def commit(self):
            self.committed = True

        def rollback(self):
            self.rolled_back = True

    session = FakeSession()

    @contextmanager
    def fake_db_session():
        try:
            yield session
        finally:
            session.exited = True

    service = Mock(return_value=profile)
    trigger = Mock()

    def trigger_after_commit(download_profile_id):
        assert session.committed is True
        assert session.exited is True
        trigger(download_profile_id)

    monkeypatch.setattr(module, "db_session", fake_db_session)
    monkeypatch.setattr(module, service_name, service)
    monkeypatch.setattr(module, "_trigger_download_profile_worker", trigger_after_commit)

    endpoint = getattr(module, endpoint_name)
    if is_update:
        result = endpoint(profile.id, object())
    else:
        result = endpoint(object())

    assert result is profile
    assert session.rolled_back is False
    trigger.assert_called_once_with(profile.id)


@pytest.mark.parametrize(
    "module_name",
    [
        "backend.api.endpoints.podcast_download_profiles.router",
        "backend.api.endpoints.series_download_profiles.router",
    ],
)
def test_download_profile_trigger_targets_only_changed_profile(monkeypatch, module_name):
    module = importlib.import_module(module_name)
    executor = importlib.import_module("task_manager.scheduler.executor")
    trigger_now = Mock()
    monkeypatch.setattr(executor, "trigger_now", trigger_now)

    module._trigger_download_profile_worker(91)

    trigger_now.assert_called_once_with(
        def_key="download_profile_worker",
        resource_type="download_profile",
        resource_id=91,
    )


def test_download_profile_worker_does_not_subscribe_to_profile_write_events():
    from task_manager.tasks.workers.download_profile_worker import download_profile_worker

    event_names = {
        trigger.event_name
        for trigger in download_profile_worker._task_meta.triggers
        if trigger.trigger_type == "event"
    }

    assert "show.indexed" in event_names
    assert "download_profile.added" not in event_names
    assert "download_profile.updated" not in event_names
