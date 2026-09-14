from __future__ import annotations

import socket
from types import SimpleNamespace
from urllib.error import URLError

import pytest
from sqlalchemy import select


def _dns_error() -> URLError:
    return URLError(
        socket.gaierror(socket.EAI_AGAIN, "Temporary failure in name resolution")
    )


def _install_task(monkeypatch, *, key: str, function, default_max_retries: int = 0):
    import task_manager.scheduler.registry as registry_module

    monkeypatch.setattr(registry_module, "_REGISTRY", {})
    decorated = registry_module.task(
        key=key,
        title="Network test",
        description="Network outage test task",
        allowed_resource_types=("show",),
        default_max_retries=default_max_retries,
    )(function)
    registry_module.sync_registry_to_db()
    return decorated


def test_no_internet_classifier_recognizes_dns_outage() -> None:
    from config.network import is_no_internet_error

    assert is_no_internet_error(_dns_error())


def test_no_internet_classifier_recognizes_unreachable_network() -> None:
    import errno

    from config.network import is_no_internet_error

    assert is_no_internet_error(OSError(errno.ENETUNREACH, "Network is unreachable"))


def test_no_internet_classifier_recognizes_grouped_transport_error() -> None:
    from config.network import is_no_internet_error

    grouped = ExceptionGroup(
        "request failed",
        [RuntimeError("secondary error"), _dns_error()],
    )
    assert is_no_internet_error(grouped)


def test_no_internet_classifier_recognizes_external_process_dns_message() -> None:
    from config.network import message_indicates_no_internet

    assert message_indicates_no_internet("ffmpeg: Failed to resolve hostname example.invalid")
    assert message_indicates_no_internet("curl: (6) Could not resolve host: example.invalid")


def test_no_internet_classifier_does_not_hide_remote_service_errors() -> None:
    from config.network import is_no_internet_error

    assert not is_no_internet_error(TimeoutError("request timed out"))
    assert not is_no_internet_error(ConnectionRefusedError("connection refused"))
    assert not is_no_internet_error(RuntimeError("HTTP 503 from upstream"))


def test_scheduler_suppresses_only_no_internet_traceback(monkeypatch) -> None:
    import task_manager.scheduler.executor as executor_module
    from config.network import NoInternetConnectionError
    from task_manager.scheduler.scheduler import _execute_task_job

    def offline(**_kwargs) -> None:
        raise NoInternetConnectionError()

    monkeypatch.setattr(executor_module, "execute_task", offline)
    _execute_task_job(def_key="test", resource_type="show", resource_id=1)

    def broken(**_kwargs) -> None:
        raise RuntimeError("application bug")

    monkeypatch.setattr(executor_module, "execute_task", broken)
    with pytest.raises(RuntimeError, match="application bug"):
        _execute_task_job(def_key="test", resource_type="show", resource_id=1)


def test_task_outage_is_logged_and_persisted_cleanly(task_database, monkeypatch, caplog) -> None:
    from config.network import NO_INTERNET_CONNECTION_MESSAGE, NoInternetConnectionError
    from task_manager.scheduler.db import TaskRun
    from task_manager.scheduler.executor import execute_task

    async def worker(*, resource_id=None, progress=None):
        raise _dns_error()

    _install_task(monkeypatch, key="test_network_outage", function=worker)

    with pytest.raises(NoInternetConnectionError, match=NO_INTERNET_CONNECTION_MESSAGE):
        execute_task(
            def_key="test_network_outage",
            resource_type="show",
            resource_id=1,
            max_retries=0,
        )

    with task_database() as session:
        run = session.execute(select(TaskRun)).scalar_one()
        assert run.status == "FAILED"
        assert run.last_error == NO_INTERNET_CONNECTION_MESSAGE
        assert run.message == f"Failed after 1 attempts: {NO_INTERNET_CONNECTION_MESSAGE}"

    assert NO_INTERNET_CONNECTION_MESSAGE in caplog.text
    assert "Temporary failure in name resolution" not in caplog.text


def test_tmdb_dns_outage_does_not_retry_locally(monkeypatch) -> None:
    from backend.integrations import tmdb

    calls = 0

    def offline(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        raise _dns_error()

    monkeypatch.setattr(tmdb, "urlopen", offline)
    client = tmdb.TMDbClient(access_token="token", max_retries=3)

    with pytest.raises(tmdb.TMDbAPIError, match="No internet connection"):
        client.lookup_movie(title="Example")

    assert calls == 1


def test_rss_stream_outage_is_not_downgraded_to_episode_502() -> None:
    from backend.api.endpoints.feeds import service
    from backend.types.dailywire_user_info import WlDwMembershipLevel
    from config.network import is_no_internet_error
    from dailywire_api.dw_api.client import MiddlewareAPIError

    outage = MiddlewareAPIError("Network error: temporary DNS failure")
    outage.__cause__ = _dns_error()

    class FakeClient:
        def get_episode_details(self, slug, *, require_member_exclusive):
            raise outage

    profile = SimpleNamespace(
        show=SimpleNamespace(membership_level=WlDwMembershipLevel.FREE.value),
        preferred_format="720p",
    )
    episode = SimpleNamespace(slug="example-episode")

    with pytest.raises(MiddlewareAPIError) as exc_info:
        service.get_dailywire_stream_url(profile, episode, client=FakeClient())

    assert is_no_internet_error(exc_info.value)
