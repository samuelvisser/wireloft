from __future__ import annotations

import asyncio
from importlib import import_module
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy.orm import Session


@pytest.fixture
def scope_helpers():
    return import_module("task_manager.tasks.workers.fetch_new_episodes._helpers")


@pytest.fixture
def shows():
    return [
        SimpleNamespace(id=1, slug="first-show", title="First Show"),
        SimpleNamespace(id=17, slug="second-show", title="Second Show"),
    ]


@pytest.mark.parametrize("show_id", [None, 0])
@pytest.mark.parametrize("show_count", [0, 2])
def test_global_scope_selects_all_shows(scope_helpers, shows, show_id, show_count):
    session = Mock(spec=Session)
    session.get.return_value = None
    expected = shows[:show_count]
    session.scalars.return_value.all.return_value = expected

    assert scope_helpers.get_shows(
        session, show_id=show_id, show_slug=None,
    ) == expected
    session.scalars.assert_called_once()
    session.scalar.assert_not_called()
    session.get.assert_not_called()


@pytest.mark.parametrize("show_id", [1, 17, 999, -1])
def test_explicit_id_never_falls_back_to_all_shows(scope_helpers, shows, show_id):
    session = Mock(spec=Session)
    show = next((item for item in shows if item.id == show_id), None)
    session.get.return_value = show

    assert scope_helpers.get_shows(
        session, show_id=show_id, show_slug=None,
    ) == ([show] if show is not None else [])
    session.get.assert_called_once_with(scope_helpers.Show, show_id)
    session.scalar.assert_not_called()
    session.scalars.assert_not_called()


@pytest.mark.parametrize("show_id", [None, 0, 17])
@pytest.mark.parametrize("show_slug", ["first-show", "missing-show"])
def test_slug_scope_takes_precedence_without_global_fallback(
    scope_helpers, shows, show_id, show_slug,
):
    session = Mock(spec=Session)
    show = next((item for item in shows if item.slug == show_slug), None)
    session.scalar.return_value = show

    assert scope_helpers.get_shows(
        session, show_id=show_id, show_slug=show_slug,
    ) == ([show] if show is not None else [])
    session.scalar.assert_called_once()
    statement = session.scalar.call_args.args[0]
    assert statement.whereclause.compare(scope_helpers.Show.slug == show_slug)
    session.get.assert_not_called()
    session.scalars.assert_not_called()


@pytest.mark.parametrize("show_id", [0, None])
def test_global_scan_processes_every_show(monkeypatch, shows, show_id):
    service = import_module("task_manager.tasks.workers.fetch_new_episodes.service")
    session = Mock(spec=Session)
    session.scalars.return_value.all.return_value = shows
    by_id = {show.id: show for show in shows}
    session.get.side_effect = lambda _model, identity: by_id.get(identity)

    auth = Mock()
    auth.get_token.return_value = None
    monkeypatch.setattr(service, "DeviceAuthClient", Mock(return_value=auth))
    monkeypatch.setattr(service, "MiddlewareClient", Mock())
    fetch_show = AsyncMock(side_effect=[2, 1])
    monkeypatch.setattr(service, "_fetch_show", fetch_show)

    # Exercise the real selector and service with the cron's exact resource ID;
    # remote episode retrieval is intentionally isolated from this scope test.
    result = asyncio.run(service.run_fetch_new_episodes(session, show_id=show_id))

    assert result.shows_scanned == 2
    assert result.episodes_found == 3
    assert [show.show_id for show in result.shows] == [1, 17]
    assert fetch_show.await_count == 2
    assert [call.kwargs["show"].id for call in fetch_show.await_args_list] == [1, 17]
    assert result.as_data()["shows"] == [
        {"show_id": 1, "show_slug": "first-show", "show_title": "First Show", "episodes_found": 2},
        {"show_id": 17, "show_slug": "second-show", "show_title": "Second Show", "episodes_found": 1},
    ]
