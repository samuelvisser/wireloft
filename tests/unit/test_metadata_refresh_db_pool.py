from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace


def _final_episode(*, episode_id: int = 71):
    from backend.types.dailywire_user_info import WlDwMembershipLevel
    from backend.types.episode_types import EpisodePublishStatus

    return SimpleNamespace(
        id=episode_id,
        slug="test-episode",
        metadata_is_final=False,
        publish_status=EpisodePublishStatus.PUBLISHED_FINAL.value,
        published_date=datetime(2026, 9, 8, tzinfo=timezone.utc),
        show=SimpleNamespace(membership_level=WlDwMembershipLevel.FREE.value),
    )


def test_metadata_refresh_releases_read_transaction_before_dailywire_request(monkeypatch):
    from task_manager.tasks.workers.refresh_episode_metadata import service

    episode = _final_episode()

    class FakeSession:
        def __init__(self):
            self.get_calls = 0
            self.rollbacks = 0
            self.commits = 0
            self.transaction_open = False

        def get(self, _model, episode_id):
            assert episode_id == episode.id
            self.get_calls += 1
            self.transaction_open = True
            return episode

        def rollback(self):
            self.rollbacks += 1
            self.transaction_open = False

        def commit(self):
            self.commits += 1
            self.transaction_open = False

    session = FakeSession()
    detail = object()
    applied = []

    def fake_fetch(*, episode_slug, require_member_exclusive):
        assert episode_slug == episode.slug
        assert require_member_exclusive is False
        assert session.transaction_open is False
        return detail

    monkeypatch.setattr(service, "_fetch_episode_from_dailywire", fake_fetch)
    monkeypatch.setattr(
        service,
        "_refresh_episode_from_dailywire",
        lambda _session, refreshed_episode, fetched_detail: (
            applied.append((refreshed_episode, fetched_detail)) or True
        ),
    )
    monkeypatch.setattr(
        service,
        "schedule_remaining_metadata_checks",
        lambda **_kwargs: ["future-refresh"],
    )
    monkeypatch.setattr(service, "metadata_watch_expired", lambda *_args, **_kwargs: False)

    did_refresh = asyncio.run(
        service.run_refresh_episode_metadata(
            session,
            episode_id=episode.id,
            refresh=True,
        )
    )

    assert did_refresh is True
    assert session.rollbacks == 1
    assert session.get_calls == 2
    assert session.commits == 1
    assert applied == [(episode, detail)]


def test_metadata_refresh_revalidates_episode_after_dailywire_request(monkeypatch):
    from backend.types.episode_types import EpisodePublishStatus
    from task_manager.tasks.workers.refresh_episode_metadata import service

    initial = _final_episode(episode_id=72)
    changed = SimpleNamespace(
        **{
            **initial.__dict__,
            "publish_status": EpisodePublishStatus.LIVE.value,
        }
    )

    class FakeSession:
        def __init__(self):
            self.get_calls = 0
            self.rollbacks = 0

        def get(self, _model, episode_id):
            assert episode_id == initial.id
            self.get_calls += 1
            return initial if self.get_calls == 1 else changed

        def rollback(self):
            self.rollbacks += 1

    session = FakeSession()
    applied = []
    monkeypatch.setattr(service, "_fetch_episode_from_dailywire", lambda **_kwargs: object())
    monkeypatch.setattr(
        service,
        "_refresh_episode_from_dailywire",
        lambda *_args: applied.append(True) or True,
    )

    did_refresh = asyncio.run(
        service.run_refresh_episode_metadata(
            session,
            episode_id=initial.id,
            refresh=True,
        )
    )

    assert did_refresh is False
    assert session.rollbacks == 1
    assert session.get_calls == 2
    assert applied == []
