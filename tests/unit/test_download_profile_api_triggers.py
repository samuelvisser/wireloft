from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _make_show(session: Session, *, slug: str, show_type: str):
    from backend.db.models import Show
    from backend.types.show_types import EpisodeIdentifier

    show = Show(
        uuid=f"{slug}-uuid",
        slug=slug,
        title="Test Show",
        description=None,
        sharing_url=f"https://example.test/{slug}",
        membership_level="FREE",
        type=show_type,
        episode_identifier=EpisodeIdentifier.NUMBERED.value,
        author_name="Host",
        author_slug="host",
    )
    session.add(show)
    session.flush()
    return show


def _make_local_media_profile(session: Session, *, slug: str):
    from backend.db.models import LocalMediaProfile

    profile = LocalMediaProfile(
        slug=slug,
        name=slug,
        output_template="/downloads/{show}/{episode}.ext",
        preferred_format="format_audio_only",
    )
    session.add(profile)
    session.flush()
    return profile


@pytest.fixture
def db_session():
    from backend.db import Base
    from backend.db.core import load_database_models

    load_database_models()
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()
    engine.dispose()


def _capture_event(event_name: str) -> list[dict]:
    from task_manager.events.registry import WireloftEventLinker

    observed: list[dict] = []
    WireloftEventLinker.subscribe(
        event_name,
        event_callback=lambda **event_data: observed.append(event_data),
    )
    return observed


def test_podcast_profile_create_and_update_fire_transactional_events(db_session):
    from backend.api.endpoints.podcast_download_profiles.service import (
        create_download_profile_podcast,
        update_download_profile_podcast,
    )
    from backend.api.models.podcast_download_profile import (
        PodcastDownloadProfileAPICreate,
        PodcastDownloadProfileAPIUpdate,
    )
    from backend.types.download_profile_types import EpIdType
    from backend.types.show_types import ShowType
    from task_manager.events.registry import WireloftEventLinker, wait_for_events

    show = _make_show(db_session, slug="podcast", show_type=ShowType.PODCAST.value)
    media_profile = _make_local_media_profile(db_session, slug="podcast-audio")

    added = _capture_event("download_profile.added")
    created = create_download_profile_podcast(
        db_session,
        PodcastDownloadProfileAPICreate(
            show_id=show.id,
            local_media_profile_id=media_profile.id,
            enable_profile=True,
            ep_id_type_list=[EpIdType.EP.value],
            download_with_countdown=False,
            redownload_final=False,
            download_days_in_past=0,
            download_episode_count=0,
            delete_older_episodes=False,
        ),
    )

    assert added == []
    db_session.commit()
    wait_for_events()
    assert added == [{
        "resource_id": created.id,
        "id": created.id,
        "show_id": show.id,
        "profile_type": "podcast",
    }]

    WireloftEventLinker.remove_all()
    updated = _capture_event("download_profile.updated")
    result = update_download_profile_podcast(
        db_session,
        created.id,
        PodcastDownloadProfileAPIUpdate(
            local_media_profile_id=media_profile.id,
            enable_profile=True,
            ep_id_type_list=[EpIdType.EP.value],
            download_with_countdown=True,
            redownload_final=False,
            download_days_in_past=0,
            download_episode_count=0,
            delete_older_episodes=False,
        ),
    )

    assert updated == []
    db_session.commit()
    wait_for_events()
    assert result.id == created.id
    assert updated == [{
        "resource_id": created.id,
        "id": created.id,
        "show_id": show.id,
        "profile_type": "podcast",
    }]


def test_series_profile_create_and_update_fire_transactional_events(db_session):
    from backend.api.endpoints.series_download_profiles.service import (
        create_download_profile_series,
        update_download_profile_series,
    )
    from backend.api.models.season import SeasonAPIRequestDetached
    from backend.api.models.series_download_profile import (
        SeriesDownloadProfileAPICreate,
        SeriesDownloadProfileAPIUpdate,
    )
    from backend.db.models import Season
    from backend.types.download_profile_types import EpIdType
    from backend.types.show_types import ShowType
    from task_manager.events.registry import WireloftEventLinker, wait_for_events

    show = _make_show(db_session, slug="series", show_type=ShowType.SERIES.value)
    media_profile = _make_local_media_profile(db_session, slug="series-video")
    season = Season(show=show, index=1, slug="season-1", name="Season 1")
    db_session.add(season)
    db_session.flush()
    season_input = SeasonAPIRequestDetached(name=season.name, slug=season.slug)

    added = _capture_event("download_profile.added")
    created = create_download_profile_series(
        db_session,
        SeriesDownloadProfileAPICreate(
            show_id=show.id,
            local_media_profile_id=media_profile.id,
            enable_profile=True,
            ep_id_type_list=[EpIdType.EP.value],
            seasons=[season_input],
            include_upcoming_seasons=False,
        ),
    )

    assert added == []
    db_session.commit()
    wait_for_events()
    assert added == [{
        "resource_id": created.id,
        "id": created.id,
        "show_id": show.id,
        "profile_type": "series",
    }]

    WireloftEventLinker.remove_all()
    updated = _capture_event("download_profile.updated")
    result = update_download_profile_series(
        db_session,
        created.id,
        SeriesDownloadProfileAPIUpdate(
            local_media_profile_id=media_profile.id,
            enable_profile=True,
            ep_id_type_list=[EpIdType.EP.value],
            seasons=[season_input],
            include_upcoming_seasons=True,
        ),
    )

    assert updated == []
    db_session.commit()
    wait_for_events()
    assert result.id == created.id
    assert updated == [{
        "resource_id": created.id,
        "id": created.id,
        "show_id": show.id,
        "profile_type": "series",
    }]


def test_download_profile_events_are_discarded_on_rollback(db_session):
    from backend.api.endpoints.podcast_download_profiles.service import create_download_profile_podcast
    from backend.api.models.podcast_download_profile import PodcastDownloadProfileAPICreate
    from backend.types.download_profile_types import EpIdType
    from backend.types.show_types import ShowType
    from task_manager.events.registry import wait_for_events

    show = _make_show(db_session, slug="rolled-back", show_type=ShowType.PODCAST.value)
    media_profile = _make_local_media_profile(db_session, slug="rolled-back-audio")
    added = _capture_event("download_profile.added")

    create_download_profile_podcast(
        db_session,
        PodcastDownloadProfileAPICreate(
            show_id=show.id,
            local_media_profile_id=media_profile.id,
            enable_profile=True,
            ep_id_type_list=[EpIdType.EP.value],
            download_with_countdown=False,
            redownload_final=False,
            download_days_in_past=0,
            download_episode_count=0,
            delete_older_episodes=False,
        ),
    )
    db_session.rollback()
    wait_for_events()

    assert added == []


def test_download_profile_worker_subscribes_to_profile_write_events():
    from task_manager.tasks.workers.download_profile_worker import download_profile_worker

    event_names = {
        trigger.event_name
        for trigger in download_profile_worker._task_meta.triggers
        if trigger.trigger_type == "event"
    }

    assert "show.indexed" in event_names
    assert "download_profile.added" in event_names
    assert "download_profile.updated" in event_names


def test_download_profile_event_dispatches_exact_profile_to_worker(monkeypatch):
    import task_manager.scheduler.executor as executor_module
    import task_manager.scheduler.registry as registry_module
    import task_manager.scheduler.scheduler as scheduler_module
    from config import get_settings
    from controller.app import setup_triggers_from_registry
    from task_manager.events.emitters import emit_event
    from task_manager.events.registry import wait_for_events

    download_profile_task = registry_module.get_task("download_profile_worker")
    monkeypatch.setattr(
        registry_module,
        "_REGISTRY",
        {"download_profile_worker": download_profile_task},
    )
    monkeypatch.setattr(get_settings().scheduler, "enabled", True)

    trigger_now = Mock()
    monkeypatch.setattr(executor_module, "trigger_now", trigger_now)

    class FakeScheduler:
        def __init__(self) -> None:
            self.jobs: dict[str, SimpleNamespace] = {}

        def add_job(self, function, **kwargs):
            job_id = kwargs.get("id", f"job-{len(self.jobs) + 1}")
            job_data = dict(kwargs)
            job_data["id"] = job_id
            job_data["function"] = function
            job = SimpleNamespace(**job_data)
            self.jobs[job_id] = job
            return job

    fake_scheduler = FakeScheduler()
    monkeypatch.setattr(scheduler_module, "start_scheduler", lambda: fake_scheduler)

    setup_triggers_from_registry()
    emit_event("download_profile.updated", {
        "resource_id": 91,
        "id": 91,
        "show_id": 12,
        "profile_type": "podcast",
    })
    wait_for_events()

    trigger_now.assert_called_once_with(
        def_key="download_profile_worker",
        resource_type="download_profile",
        resource_id=91,
    )
