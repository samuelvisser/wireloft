from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


# ---------- detection ----------

def test_is_no_show_today_title_matches_case_insensitively():
    from task_manager.tasks.helpers.episodes.no_show import is_no_show_today_title

    assert is_no_show_today_title("The Matt Walsh Show - No Show Today") is True
    assert is_no_show_today_title("no show today") is True
    assert is_no_show_today_title("NO SHOW TODAY") is True
    assert is_no_show_today_title("The Matt Walsh Show - Episode 1809") is False
    assert is_no_show_today_title("") is False
    assert is_no_show_today_title(None) is False


# ---------- shared fixtures ----------

def _make_show(session, *, slug="test-show"):
    from backend.db.models import Show
    from backend.types.show_types import EpisodeIdentifier, ShowType

    show = Show(
        uuid=f"{slug}-uuid",
        slug=slug,
        title="Test Show",
        description=None,
        sharing_url=f"https://example.test/{slug}",
        membership_level="FREE",
        type=ShowType.PODCAST.value,
        episode_identifier=EpisodeIdentifier.NUMBERED.value,
        author_name="Host",
        author_slug="host",
    )
    session.add(show)
    session.flush()
    return show


def _make_season(session, show, *, index=1, slug="season-1", name="One"):
    from backend.db.models import Season

    season = Season(show=show, index=index, slug=slug, name=name)
    session.add(season)
    session.flush()
    return season


def _make_episode(session, show, season, *, slug, ep_id, title, index, is_no_show_today=False):
    from backend.db.models import Episode
    from backend.utils.helpers import generate_uuid

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    episode = Episode(
        uuid=generate_uuid(),
        type="episode",
        show=show,
        season=season,
        index=index,
        episode_identifier=ep_id,
        slug=slug,
        title=title,
        duration=100.0,
        publish_status="published_final",
        sharing_url=f"https://example.test/{slug}",
        published_date=now,
        is_no_show_today=is_no_show_today,
    )
    session.add(episode)
    session.flush()
    return episode


def _make_local_media_profile(session, *, slug="audio"):
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
    import backend.db.models  # noqa: F401 (registers all mappers before create_all)
    from backend.db import Base

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()
    engine.dispose()


# ---------- upsert_episode sets the flag ----------

def _dw_episode_record(slug: str, title: str):
    from dailywire_api.records import DwEpisodeRecord
    from datetime import datetime, timezone

    return DwEpisodeRecord(
        dw_id=f"remote-{slug}",
        slug=slug,
        title=title,
        description=None,
        duration=100,
        episode_number="1.00",
        display_episode_number="1",
        background_image_path=None,
        sharing_url=f"https://example.test/{slug}",
        publish_status="PUBLISHED",
        is_downloadable=True,
        available_for=[],
        thumbnail_landscape_path=None,
        thumbnail_portrait_path=None,
        thumbnail_square_path=None,
        published_date=datetime(2026, 1, 1, tzinfo=timezone.utc),
        scheduled_date=None,
    )


def test_upsert_episode_flags_no_show_today_on_create(db_session):
    from task_manager.tasks.helpers.episodes.save import upsert_episode

    show = _make_show(db_session)
    season = _make_season(db_session, show)

    ep = _dw_episode_record("matt-walsh-ep-1809-no-show-today", "The Matt Walsh Show - No Show Today")
    episode = upsert_episode(db_session, show=show, season=season, ep=ep, index_value=1, ep_id="ep.1809")

    assert episode.is_no_show_today is True


def test_upsert_episode_does_not_flag_a_real_episode(db_session):
    from task_manager.tasks.helpers.episodes.save import upsert_episode

    show = _make_show(db_session)
    season = _make_season(db_session, show)

    ep = _dw_episode_record("matt-walsh-ep-1810", "Episode 1810: The Real Deal")
    episode = upsert_episode(db_session, show=show, season=season, ep=ep, index_value=1, ep_id="ep.1810")

    assert episode.is_no_show_today is False


def test_upsert_episode_reflags_on_update(db_session):
    """Re-indexing an existing episode must recompute the flag too, not just set it once."""
    from task_manager.tasks.helpers.episodes.save import upsert_episode

    show = _make_show(db_session)
    season = _make_season(db_session, show)

    ep = _dw_episode_record("matt-walsh-ep-1809", "Episode 1809")
    episode = upsert_episode(db_session, show=show, season=season, ep=ep, index_value=1, ep_id="ep.1809")
    assert episode.is_no_show_today is False

    renamed = _dw_episode_record("matt-walsh-ep-1809", "The Matt Walsh Show - No Show Today")
    episode = upsert_episode(db_session, show=show, season=season, ep=renamed, index_value=1, ep_id="ep.1809")
    assert episode.is_no_show_today is True


# ---------- excluded from download profile eligibility ----------

def test_get_download_profile_episodes_excludes_no_show_today(db_session):
    from task_manager.tasks.workers.download_profile_worker._helpers import get_download_profile_episodes
    from backend.db.models.download_profile import PodcastDownloadProfile
    from backend.types.download_profile_types import EpIdType

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    lmp = _make_local_media_profile(db_session)

    real_ep = _make_episode(db_session, show, season, slug="ep-real", ep_id="ep.1", title="Real episode", index=1)
    no_show_ep = _make_episode(
        db_session, show, season, slug="ep-no-show", ep_id="aux.1", title="No Show Today", index=2, is_no_show_today=True,
    )

    profile = PodcastDownloadProfile(
        show=show, local_media_profile=lmp, type="podcast", enable_profile=True,
        ep_id_type_list=[EpIdType.EP.value, EpIdType.AUX.value],
        download_with_countdown=False, redownload_final=False, download_days_in_past=0, delete_older_episodes=False,
    )
    db_session.add(profile)
    db_session.commit()

    episodes = get_download_profile_episodes(db_session, profile)
    slugs = {e.slug for e in episodes}
    assert real_ep.slug in slugs
    assert no_show_ep.slug not in slugs


# ---------- manual download creation is rejected too ----------

def test_create_episode_download_rejects_no_show_today_episode(db_session):
    from fastapi import HTTPException
    from backend.api.endpoints.media_downloads.service import create_episode_download
    from backend.api.models.media_download import EpisodeDownloadAPICreate

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    lmp = _make_local_media_profile(db_session)
    episode = _make_episode(
        db_session, show, season, slug="ep-no-show", ep_id="aux.1", title="No Show Today", index=1, is_no_show_today=True,
    )
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        create_episode_download(db_session, episode.slug, EpisodeDownloadAPICreate(local_media_profile_id=lmp.id))
    assert exc_info.value.status_code == 422


# ---------- deletion once Daily Wire removes it ----------

def test_check_no_show_today_deletes_when_dw_returns_404(db_session, monkeypatch):
    from task_manager.tasks.workers.check_no_show_today_episodes import service
    from dailywire_api.dw_api.client import MiddlewareAPIError
    from backend.db.models import Episode

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    episode = _make_episode(
        db_session, show, season, slug="ep-no-show", ep_id="aux.1", title="No Show Today", index=1, is_no_show_today=True,
    )
    db_session.commit()
    episode_id = episode.id

    class FakeClient:
        def __init__(self, access_token=None):
            pass

        def get_episode_details(self, slug, *, require_member_exclusive):
            raise MiddlewareAPIError("HTTP error 404: episode not found", status_code=404)

    monkeypatch.setattr(service, "MiddlewareClient", FakeClient)
    monkeypatch.setattr(service, "DeviceAuthClient", lambda: Mock(get_token=lambda: None))

    asyncio.run(service.run_check_no_show_today_episodes(db_session))

    assert db_session.get(Episode, episode_id) is None


def test_check_no_show_today_keeps_episode_when_dw_still_has_it(db_session, monkeypatch):
    from task_manager.tasks.workers.check_no_show_today_episodes import service
    from backend.db.models import Episode

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    episode = _make_episode(
        db_session, show, season, slug="ep-no-show", ep_id="aux.1", title="No Show Today", index=1, is_no_show_today=True,
    )
    db_session.commit()
    episode_id = episode.id

    class FakeClient:
        def __init__(self, access_token=None):
            pass

        def get_episode_details(self, slug, *, require_member_exclusive):
            return object()

    monkeypatch.setattr(service, "MiddlewareClient", FakeClient)
    monkeypatch.setattr(service, "DeviceAuthClient", lambda: Mock(get_token=lambda: None))

    asyncio.run(service.run_check_no_show_today_episodes(db_session))

    assert db_session.get(Episode, episode_id) is not None


def test_check_no_show_today_ignores_a_real_episode_even_if_deleted_remotely(db_session, monkeypatch):
    """Only "No Show Today" episodes get auto-deleted; real episodes are kept
    even if a check for some other reason reported them missing."""
    from task_manager.tasks.workers.check_no_show_today_episodes import service
    from backend.db.models import Episode

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    real_episode = _make_episode(
        db_session, show, season, slug="ep-real", ep_id="ep.1", title="Real Episode", index=1, is_no_show_today=False,
    )
    db_session.commit()
    real_episode_id = real_episode.id

    called = Mock()
    monkeypatch.setattr(service, "MiddlewareClient", lambda access_token=None: called)

    asyncio.run(service.run_check_no_show_today_episodes(db_session))

    called.get_episode_details.assert_not_called()
    assert db_session.get(Episode, real_episode_id) is not None


def test_check_no_show_today_skips_premium_show_without_token(db_session, monkeypatch):
    from task_manager.tasks.workers.check_no_show_today_episodes import service
    from backend.db.models import Episode

    show = _make_show(db_session, slug="premium-show")
    show.membership_level = "ALL_ACCESS"
    season = _make_season(db_session, show)
    episode = _make_episode(
        db_session, show, season, slug="ep-no-show", ep_id="aux.1", title="No Show Today", index=1, is_no_show_today=True,
    )
    db_session.commit()
    episode_id = episode.id

    client_calls = Mock()
    monkeypatch.setattr(service, "MiddlewareClient", lambda access_token=None: client_calls)
    monkeypatch.setattr(service, "DeviceAuthClient", lambda: Mock(get_token=lambda: None))

    asyncio.run(service.run_check_no_show_today_episodes(db_session))

    client_calls.get_episode_details.assert_not_called()
    assert db_session.get(Episode, episode_id) is not None


def test_check_no_show_today_noop_when_none_flagged(db_session, monkeypatch):
    from task_manager.tasks.workers.check_no_show_today_episodes import service

    called = Mock()
    monkeypatch.setattr(service, "MiddlewareClient", called)

    asyncio.run(service.run_check_no_show_today_episodes(db_session))

    called.assert_not_called()
