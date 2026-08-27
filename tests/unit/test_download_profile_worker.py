from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


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


def _make_episode(session, show, season, *, slug, ep_id, status, published_at, index):
    from backend.db.models import Episode
    from backend.utils.helpers import generate_uuid

    episode = Episode(
        uuid=generate_uuid(),
        type="episode",
        show=show,
        season=season,
        index=index,
        episode_identifier=ep_id,
        slug=slug,
        title=f"Episode {slug}",
        duration=100.0,
        publish_status=status,
        sharing_url=f"https://example.test/{slug}",
        published_date=published_at,
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


def _make_podcast_profile(session, show, lmp, **overrides):
    from backend.db.models.download_profile import PodcastDownloadProfile
    from backend.types.download_profile_types import EpIdType

    defaults = dict(
        show=show,
        local_media_profile=lmp,
        type="podcast",
        enable_profile=True,
        ep_id_type_list=[EpIdType.EP.value],
        download_with_countdown=False,
        redownload_final=False,
        download_days_in_past=0,
        delete_older_episodes=False,
    )
    defaults.update(overrides)
    profile = PodcastDownloadProfile(**defaults)
    session.add(profile)
    session.flush()
    return profile


def _make_series_profile(session, show, lmp, seasons, **overrides):
    from backend.db.models.download_profile import SeriesDownloadProfile
    from backend.types.download_profile_types import EpIdType

    defaults = dict(
        show=show,
        local_media_profile=lmp,
        type="series",
        enable_profile=True,
        ep_id_type_list=[EpIdType.EP.value],
        include_upcoming_seasons=False,
    )
    defaults.update(overrides)
    profile = SeriesDownloadProfile(**defaults)
    profile.seasons = seasons
    session.add(profile)
    session.flush()
    return profile


@pytest.fixture
def db_session(monkeypatch, tmp_path):
    import backend.db.models  # noqa: F401 (registers all mappers before create_all)
    from backend.db import Base
    from config import get_settings

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)
    yield session
    session.close()
    engine.dispose()


# ---------- get_download_profile_episodes ----------

def test_podcast_profile_filters_by_type_status_and_countdown(db_session):
    from task_manager.tasks.workers.download_profile_worker._helpers import get_download_profile_episodes

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    lmp = _make_local_media_profile(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    final_ep = _make_episode(db_session, show, season, slug="final", ep_id="ep.1", status="published_final", published_at=now, index=1)
    countdown_ep = _make_episode(db_session, show, season, slug="countdown", ep_id="ep.2", status="published_with_countdown", published_at=now, index=2)
    live_ep = _make_episode(db_session, show, season, slug="live", ep_id="ep.3", status="live", published_at=now, index=3)
    trailer_ep = _make_episode(db_session, show, season, slug="trailer", ep_id="trailer.1", status="published_final", published_at=now, index=4)

    profile = _make_podcast_profile(db_session, show, lmp, download_with_countdown=False)

    episodes = get_download_profile_episodes(db_session, profile)
    assert {e.slug for e in episodes} == {"final"}

    profile.download_with_countdown = True
    episodes = get_download_profile_episodes(db_session, profile)
    assert {e.slug for e in episodes} == {"final", "countdown"}
    assert live_ep.slug not in {e.slug for e in episodes}
    assert trailer_ep.slug not in {e.slug for e in episodes}


def test_podcast_profile_respects_days_in_past_window(db_session):
    from task_manager.tasks.workers.download_profile_worker._helpers import get_download_profile_episodes

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    lmp = _make_local_media_profile(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    recent = _make_episode(db_session, show, season, slug="recent", ep_id="ep.1", status="published_final", published_at=now - timedelta(days=1), index=1)
    old = _make_episode(db_session, show, season, slug="old", ep_id="ep.2", status="published_final", published_at=now - timedelta(days=30), index=2)

    profile = _make_podcast_profile(db_session, show, lmp, download_days_in_past=7)

    episodes = get_download_profile_episodes(db_session, profile)
    assert {e.slug for e in episodes} == {"recent"}

    profile.download_days_in_past = 0
    episodes = get_download_profile_episodes(db_session, profile)
    assert {e.slug for e in episodes} == {"recent", "old"}


def test_series_profile_filters_by_seasons_and_upcoming(db_session):
    from task_manager.tasks.workers.download_profile_worker._helpers import get_download_profile_episodes

    show = _make_show(db_session)
    season1 = _make_season(db_session, show, index=1, slug="s1", name="One")
    season2 = _make_season(db_session, show, index=2, slug="s2", name="Two")
    season3 = _make_season(db_session, show, index=3, slug="s3", name="Three")
    lmp = _make_local_media_profile(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    ep1 = _make_episode(db_session, show, season1, slug="ep1", ep_id="ep.1", status="published_final", published_at=now, index=1)
    ep2 = _make_episode(db_session, show, season2, slug="ep2", ep_id="ep.2", status="published_final", published_at=now, index=2)
    ep3 = _make_episode(db_session, show, season3, slug="ep3", ep_id="ep.3", status="published_final", published_at=now, index=3)

    profile = _make_series_profile(db_session, show, lmp, [season1], include_upcoming_seasons=False)
    episodes = get_download_profile_episodes(db_session, profile)
    assert {e.slug for e in episodes} == {"ep1"}

    profile.include_upcoming_seasons = True
    episodes = get_download_profile_episodes(db_session, profile)
    # season2 and season3 both come after the only chosen season (index 1)
    assert {e.slug for e in episodes} == {"ep1", "ep2", "ep3"}


# ---------- ensure_episode_download ----------

def test_ensure_episode_download_creates_pending_row(db_session):
    from task_manager.tasks.workers.download_profile_worker._helpers import ensure_episode_download
    from backend.types.download_profile_types import MediaDownloadStatus

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    lmp = _make_local_media_profile(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    episode = _make_episode(db_session, show, season, slug="ep", ep_id="ep.1", status="published_final", published_at=now, index=1)
    profile = _make_podcast_profile(db_session, show, lmp)

    action = ensure_episode_download(db_session, profile, episode)
    db_session.commit()

    assert action.needs_trigger is True
    assert action.is_redownload is False

    from backend.db.models.media_download import EpisodeMediaDownload
    row = db_session.get(EpisodeMediaDownload, action.media_download_id)
    assert row.download_status == MediaDownloadStatus.PENDING.value
    assert row.download_profile_id == profile.id


def test_ensure_episode_download_adopts_manual_download(db_session):
    from task_manager.tasks.workers.download_profile_worker._helpers import ensure_episode_download
    from backend.db.models.media_download import EpisodeMediaDownload
    from backend.types.download_profile_types import MediaDownloadStatus
    from backend.types.media_types import MediaType

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    lmp = _make_local_media_profile(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    episode = _make_episode(db_session, show, season, slug="ep", ep_id="ep.1", status="published_final", published_at=now, index=1)
    profile = _make_podcast_profile(db_session, show, lmp)

    manual = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=episode.id,
        local_media_profile_id=lmp.id,
        download_status=MediaDownloadStatus.DOWNLOADED.value,
        file_path="/downloads/manual.m4a",
        progress=100,
    )
    db_session.add(manual)
    db_session.commit()

    action = ensure_episode_download(db_session, profile, episode)
    db_session.commit()

    assert action.needs_trigger is False
    assert manual.download_profile_id == profile.id


def _make_completed_download(db_session, episode, lmp, profile, *, downloaded_publish_status):
    from backend.db.models.media_download import EpisodeMediaDownload
    from backend.types.download_profile_types import MediaDownloadStatus
    from backend.types.media_types import MediaType

    existing = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=episode.id,
        local_media_profile_id=lmp.id,
        download_profile_id=profile.id,
        download_status=MediaDownloadStatus.DOWNLOADED.value,
        downloaded_publish_status=downloaded_publish_status,
        file_path="/downloads/existing.m4a",
        progress=100,
    )
    db_session.add(existing)
    db_session.commit()
    return existing


def test_ensure_episode_download_redownload_final(db_session):
    from task_manager.tasks.workers.download_profile_worker._helpers import ensure_episode_download
    from backend.types.download_profile_types import MediaDownloadStatus

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    lmp = _make_local_media_profile(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    episode = _make_episode(db_session, show, season, slug="ep", ep_id="ep.1", status="published_final", published_at=now, index=1)
    profile = _make_podcast_profile(db_session, show, lmp, download_with_countdown=True, redownload_final=True)

    # The file on disk was actually fetched while still countdown-era: the only
    # case that genuinely needs replacing.
    existing = _make_completed_download(db_session, episode, lmp, profile, downloaded_publish_status="published_with_countdown")

    action = ensure_episode_download(db_session, profile, episode)
    db_session.commit()
    assert action.needs_trigger is True
    assert action.is_redownload is True
    assert existing.download_status == MediaDownloadStatus.PENDING.value

    # Once the redownload actually completes, downloaded_publish_status reflects
    # the final version fetched, so it must never be re-armed again.
    existing.download_status = MediaDownloadStatus.REDOWNLOADED.value
    existing.downloaded_publish_status = "published_final"
    db_session.commit()

    action = ensure_episode_download(db_session, profile, episode)
    assert action.needs_trigger is False


def test_ensure_episode_download_no_redownload_when_already_downloaded_final(db_session):
    """The file we have was already fetched as the final version (e.g. countdown
    downloading was off, or DW had already gone final by the time we grabbed
    it): there is nothing to replace, regardless of redownload_final."""
    from task_manager.tasks.workers.download_profile_worker._helpers import ensure_episode_download

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    lmp = _make_local_media_profile(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    episode = _make_episode(db_session, show, season, slug="ep", ep_id="ep.1", status="published_final", published_at=now, index=1)
    profile = _make_podcast_profile(db_session, show, lmp, download_with_countdown=True, redownload_final=True)

    _make_completed_download(db_session, episode, lmp, profile, downloaded_publish_status="published_final")

    action = ensure_episode_download(db_session, profile, episode)
    assert action.needs_trigger is False


def test_ensure_episode_download_no_redownload_when_countdown_downloading_disabled(db_session):
    """A profile that never downloads countdown episodes has nothing to replace
    later: the only version it ever fetches is already final."""
    from task_manager.tasks.workers.download_profile_worker._helpers import ensure_episode_download

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    lmp = _make_local_media_profile(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    episode = _make_episode(db_session, show, season, slug="ep", ep_id="ep.1", status="published_final", published_at=now, index=1)
    # redownload_final left True (as if toggled on before countdown downloading
    # was turned back off) to prove download_with_countdown alone gates this.
    profile = _make_podcast_profile(db_session, show, lmp, download_with_countdown=False, redownload_final=True)

    # Even a row that (implausibly) recorded a countdown-era fetch must not be
    # redownloaded once the profile no longer wants countdown episodes at all.
    _make_completed_download(db_session, episode, lmp, profile, downloaded_publish_status="published_with_countdown")

    action = ensure_episode_download(db_session, profile, episode)
    assert action.needs_trigger is False


# ---------- cleanup_older_episodes ----------

def test_cleanup_older_episodes_deletes_row_and_file(db_session, tmp_path):
    from task_manager.tasks.workers.download_profile_worker._helpers import cleanup_older_episodes
    from backend.db.models.media_download import EpisodeMediaDownload
    from backend.types.download_profile_types import MediaDownloadStatus
    from backend.types.media_types import MediaType

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    lmp = _make_local_media_profile(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    old_episode = _make_episode(db_session, show, season, slug="old", ep_id="ep.1", status="published_final", published_at=now - timedelta(days=30), index=1)
    recent_episode = _make_episode(db_session, show, season, slug="recent", ep_id="ep.2", status="published_final", published_at=now - timedelta(days=1), index=2)

    profile = _make_podcast_profile(db_session, show, lmp, download_days_in_past=7, delete_older_episodes=True)

    old_file = tmp_path / "old.m4a"
    old_file.write_bytes(b"data")
    recent_file = tmp_path / "recent.m4a"
    recent_file.write_bytes(b"data")

    old_download = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=old_episode.id,
        local_media_profile_id=lmp.id,
        download_profile_id=profile.id,
        download_status=MediaDownloadStatus.DOWNLOADED.value,
        file_path=str(old_file),
        progress=100,
    )
    recent_download = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=recent_episode.id,
        local_media_profile_id=lmp.id,
        download_profile_id=profile.id,
        download_status=MediaDownloadStatus.DOWNLOADED.value,
        file_path=str(recent_file),
        progress=100,
    )
    db_session.add_all([old_download, recent_download])
    db_session.commit()

    removed = cleanup_older_episodes(db_session, profile)
    db_session.commit()

    assert removed == 1
    assert not old_file.exists()
    assert recent_file.exists()
    remaining = db_session.query(EpisodeMediaDownload).all()
    assert [d.media_item_id for d in remaining] == [recent_episode.id]


# ---------- run_download_profile_worker end-to-end ----------

def test_run_worker_triggers_downloads_for_episode_scope(db_session, monkeypatch):
    from task_manager.tasks.workers.download_profile_worker import service

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    lmp = _make_local_media_profile(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    episode = _make_episode(db_session, show, season, slug="ep", ep_id="ep.1", status="published_final", published_at=now, index=1)
    _make_podcast_profile(db_session, show, lmp)
    db_session.commit()

    triggered = Mock()
    monkeypatch.setattr(service, "trigger_now", triggered)

    asyncio.run(service.run_download_profile_worker(db_session, resource_id=episode.id, resource_type="episode"))

    triggered.assert_called_once()
    _, kwargs = triggered.call_args
    assert kwargs["def_key"] == "download_episode"
    assert kwargs["resource_id"] == episode.id
    assert kwargs["is_redownload"] is False


def test_run_worker_respects_concurrency_budget(db_session, monkeypatch):
    from config import get_settings
    from task_manager.tasks.workers.download_profile_worker import service

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    lmp = _make_local_media_profile(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for i in range(3):
        _make_episode(db_session, show, season, slug=f"ep{i}", ep_id=f"ep.{i}", status="published_final", published_at=now, index=i)
    _make_podcast_profile(db_session, show, lmp)
    db_session.commit()

    monkeypatch.setattr(get_settings().download_settings, "max_concurrent_downloads", 1)
    triggered = Mock()
    monkeypatch.setattr(service, "trigger_now", triggered)

    asyncio.run(service.run_download_profile_worker(db_session, resource_id=show.id, resource_type="show"))

    assert triggered.call_count == 1

    from backend.db.models.media_download import EpisodeMediaDownload
    from backend.types.download_profile_types import MediaDownloadStatus
    rows = db_session.query(EpisodeMediaDownload).all()
    assert len(rows) == 3
    assert all(r.download_status == MediaDownloadStatus.PENDING.value for r in rows)


def test_run_worker_no_enabled_profiles_is_a_noop(db_session, monkeypatch):
    from task_manager.tasks.workers.download_profile_worker import service

    triggered = Mock()
    monkeypatch.setattr(service, "trigger_now", triggered)

    asyncio.run(service.run_download_profile_worker(db_session, resource_id=0, resource_type="download_profile"))

    triggered.assert_not_called()


# ---------- trigger_next_pending_downloads (queue draining) ----------

def _make_pending_download(db_session, episode, lmp, *, profile=None):
    from backend.db.models.media_download import EpisodeMediaDownload
    from backend.types.download_profile_types import MediaDownloadStatus
    from backend.types.media_types import MediaType

    download = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=episode.id,
        local_media_profile_id=lmp.id,
        download_profile_id=profile.id if profile else None,
        download_status=MediaDownloadStatus.PENDING.value,
        file_path=f"/downloads/{episode.slug}.m4a",
        progress=0,
    )
    db_session.add(download)
    db_session.flush()
    return download


def test_trigger_next_pending_downloads_respects_budget(db_session, monkeypatch):
    from task_manager.tasks.workers.download_profile_worker import _helpers as helpers_module

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    lmp = _make_local_media_profile(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)

    episodes = [
        _make_episode(db_session, show, season, slug=f"ep{i}", ep_id=f"ep.{i}", status="published_final", published_at=now, index=i)
        for i in range(3)
    ]
    downloads = [_make_pending_download(db_session, ep, lmp) for ep in episodes]
    db_session.commit()

    triggered = Mock()
    monkeypatch.setattr(helpers_module, "trigger_now", triggered)

    count = helpers_module.trigger_next_pending_downloads(db_session, budget=2)

    assert count == 2
    assert triggered.call_count == 2
    triggered_ids = {call.kwargs["media_download_id"] for call in triggered.call_args_list}
    assert triggered_ids == {downloads[0].id, downloads[1].id}


def test_trigger_next_pending_downloads_noop_when_budget_exhausted(db_session, monkeypatch):
    from task_manager.tasks.workers.download_profile_worker import _helpers as helpers_module

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    lmp = _make_local_media_profile(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    episode = _make_episode(db_session, show, season, slug="ep", ep_id="ep.1", status="published_final", published_at=now, index=1)
    _make_pending_download(db_session, episode, lmp)
    db_session.commit()

    triggered = Mock()
    monkeypatch.setattr(helpers_module, "trigger_now", triggered)

    count = helpers_module.trigger_next_pending_downloads(db_session, budget=0)

    assert count == 0
    triggered.assert_not_called()


def test_trigger_next_pending_downloads_derives_budget_when_not_given(db_session, monkeypatch):
    from config import get_settings
    from task_manager.tasks.workers.download_profile_worker import _helpers as helpers_module

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    lmp = _make_local_media_profile(db_session)
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    episodes = [
        _make_episode(db_session, show, season, slug=f"ep{i}", ep_id=f"ep.{i}", status="published_final", published_at=now, index=i)
        for i in range(2)
    ]
    for ep in episodes:
        _make_pending_download(db_session, ep, lmp)
    db_session.commit()

    monkeypatch.setattr(get_settings().download_settings, "max_concurrent_downloads", 1)
    triggered = Mock()
    monkeypatch.setattr(helpers_module, "trigger_now", triggered)

    count = helpers_module.trigger_next_pending_downloads(db_session)

    assert count == 1
    assert triggered.call_count == 1
