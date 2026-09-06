from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def _episode_record(
        slug: str,
        *,
        title: str = "Episode 2500",
        episode_number: str = "2500.00",
        publish_status: str = "PUBLISHED",
        published_at: datetime | None = None,
        downloadable: bool = True,
):
    from dailywire_api.records import DwEpisodeRecord

    return DwEpisodeRecord(
        dw_id=f"remote-{slug}",
        slug=slug,
        title=title,
        description=None,
        duration=3600,
        episode_number=episode_number,
        display_episode_number=episode_number,
        background_image_path=None,
        sharing_url=f"https://example.test/{slug}",
        publish_status=publish_status,
        is_downloadable=downloadable,
        available_for=[],
        thumbnail_landscape_path=None,
        thumbnail_portrait_path=None,
        thumbnail_square_path=None,
        published_date=published_at or datetime.now(timezone.utc),
        scheduled_date=None,
    )


def _episode_detail(**kwargs):
    from dailywire_api.records import DwEpisodeDetailRecord

    record = _episode_record(**kwargs)
    return DwEpisodeDetailRecord(
        **record.model_dump(mode="python", by_alias=False),
        audio_url="https://example.test/audio.mp3",
        video_url="https://example.test/video.m3u8",
        delivery_mode="VOD",
        progress=0,
        next_episode_url=None,
        playback_status=None,
    )


def test_published_final_after_minutes_is_an_absolute_fallback(monkeypatch):
    from backend.types.episode_types import EpisodePublishStatus
    from task_manager.tasks.helpers.episodes import status

    monkeypatch.setattr(
        status,
        "get_settings",
        lambda: SimpleNamespace(
            episode_status_timing=SimpleNamespace(
                published_final_after_minutes=180,
            )
        ),
    )
    detail = _episode_detail(
        slug="still-marked-live",
        publish_status="LIVE",
        published_at=datetime.now(timezone.utc) - timedelta(minutes=181),
        downloadable=False,
    )

    assert status.get_publish_status_from_dw_detail(detail) is EpisodePublishStatus.PUBLISHED_FINAL
    assert status.is_published_final(detail) is True


def test_no_show_today_overrides_absolute_final_fallback(monkeypatch):
    from backend.types.episode_types import EpisodePublishStatus
    from task_manager.tasks.helpers.episodes import status

    monkeypatch.setattr(
        status,
        "get_settings",
        lambda: SimpleNamespace(
            episode_status_timing=SimpleNamespace(
                published_final_after_minutes=180,
            )
        ),
    )
    detail = _episode_detail(
        slug="no-show",
        title="The Ben Shapiro Show - No Show Today",
        published_at=datetime.now(timezone.utc) - timedelta(days=1),
    )

    assert status.get_publish_status_from_dw_detail(detail) is EpisodePublishStatus.NO_USABLE_MEDIA
    assert status.is_published_final(detail) is False


def test_incremental_detail_404_overrides_age_fallback(monkeypatch):
    from backend.types.episode_types import EpisodePublishStatus
    from dailywire_api.dw_api.client import MiddlewareAPIError
    from task_manager.tasks.helpers.episodes import save, status
    from task_manager.tasks.helpers.episodes.unusable_media import NoUsableMediaReason

    monkeypatch.setattr(
        status,
        "get_settings",
        lambda: SimpleNamespace(
            episode_status_timing=SimpleNamespace(
                published_final_after_minutes=180,
            )
        ),
    )
    record = _episode_record(
        "missing-detail",
        published_at=datetime.now(timezone.utc) - timedelta(hours=10),
    )

    class FakeClient:
        def get_episode_details(self, slug, *, require_member_exclusive):
            raise MiddlewareAPIError("HTTP error 404: episode not found", status_code=404)

    [resolved] = save.resolve_dw_episodes(
        episodes=[("ep.2500", record)],
        client=FakeClient(),
        require_member_exclusive=False,
        always_resolve_details=True,
    )

    assert resolved.status is EpisodePublishStatus.NO_USABLE_MEDIA
    assert resolved.unusable_media_reason is NoUsableMediaReason.NOT_FOUND
    assert resolved.detail_resolved is True


def test_initial_back_catalog_can_shortcut_old_final_without_detail(monkeypatch):
    from backend.types.episode_types import EpisodePublishStatus
    from task_manager.tasks.helpers.episodes import save, status

    monkeypatch.setattr(
        status,
        "get_settings",
        lambda: SimpleNamespace(
            episode_status_timing=SimpleNamespace(
                published_final_after_minutes=180,
            )
        ),
    )
    record = _episode_record(
        "old-back-catalog",
        published_at=datetime.now(timezone.utc) - timedelta(days=100),
    )
    client = Mock()

    [resolved] = save.resolve_dw_episodes(
        episodes=[("ep.1", record)],
        client=client,
        require_member_exclusive=False,
    )

    assert resolved.status is EpisodePublishStatus.PUBLISHED_FINAL
    assert resolved.detail_resolved is False
    client.get_episode_details.assert_not_called()


def _make_show_and_episode(session, *, identifier: str):
    from backend.db.models import Episode, Season, Show
    from backend.types.show_types import EpisodeIdentifier, ShowType
    from backend.utils.helpers import generate_uuid

    show = Show(
        uuid="show-uuid",
        slug="the-ben-shapiro-show",
        title="The Ben Shapiro Show",
        description=None,
        sharing_url="https://example.test/show",
        membership_level="FREE",
        type=ShowType.PODCAST.value,
        episode_identifier=EpisodeIdentifier.NUMBERED.value,
        author_name="Ben Shapiro",
        author_slug="ben-shapiro",
    )
    season = Season(show=show, index=1, slug="2026", name="2026")
    session.add_all([show, season])
    session.flush()

    episode = Episode(
        uuid=generate_uuid(),
        type="episode",
        show=show,
        season=season,
        index=2500,
        episode_identifier=identifier,
        slug="the-ben-shapiro-show-2500",
        title="BREAKING: Judge Threatens Mistrial",
        duration=2500,
        publish_status="published_final",
        metadata_is_final=False,
        sharing_url="https://example.test/episode",
        published_date=datetime.now(timezone.utc).replace(tzinfo=None),
        is_no_show_today=False,
    )
    session.add(episode)
    show.set_meta("ep_id.latest_ep_num", "2500")
    show.set_meta("ep_id.latest_ep_extra_num", "1")
    session.commit()
    return show, episode


def test_metadata_refresh_repairs_wrong_main_episode_identifier(monkeypatch):
    import backend.db.models  # noqa: F401
    from backend.db import Base
    from task_manager.tasks.workers.refresh_episode_metadata_worker import service

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    show, episode = _make_show_and_episode(session, identifier="ep-extra.2500.1")

    detail = _episode_detail(
        slug=episode.slug,
        episode_number="2500.00",
        publish_status="PUBLISHED",
    )

    class FakeClient:
        def get_episode_details(self, slug, *, require_member_exclusive):
            assert slug == episode.slug
            return detail

    monkeypatch.setattr(service, "MiddlewareClient", FakeClient)
    monkeypatch.setattr(service, "schedule_remaining_metadata_checks", lambda **kwargs: ["pending"])
    monkeypatch.setattr(service, "remove_episode_metadata_jobs", Mock())

    asyncio.run(
        service.run_refresh_episode_metadata_worker(
            session,
            episode_id=episode.id,
            refresh=True,
        )
    )

    session.expire_all()
    stored = session.get(type(episode), episode.id)
    assert stored.episode_identifier == "ep.2500"
    assert show.get_meta("ep_id.latest_ep_num") == "2500"
    assert show.get_meta("ep_id.latest_ep_extra_num") == "0"

    session.close()
    engine.dispose()


def test_identifier_reconciliation_can_fix_extra_ordinal_after_collision_is_gone():
    import backend.db.models  # noqa: F401
    from backend.db import Base
    from task_manager.tasks.helpers.episodes.identifier import (
        reconcile_episode_identifier_from_dailywire,
    )

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    show, episode = _make_show_and_episode(session, identifier="ep-extra.2500.2")

    detail = _episode_detail(
        slug=episode.slug,
        episode_number="2500.01",
    )

    assert reconcile_episode_identifier_from_dailywire(session, episode, detail) is True
    session.commit()
    assert episode.episode_identifier == "ep-extra.2500.1"
    assert show.get_meta("ep_id.latest_ep_extra_num") == "1"

    session.close()
    engine.dispose()


def test_identifier_reconciliation_keeps_wireloft_extra_ordinal_for_dw_segment_10():
    import backend.db.models  # noqa: F401
    from backend.db import Base
    from task_manager.tasks.helpers.episodes.identifier import (
        reconcile_episode_identifier_from_dailywire,
    )

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    _show, episode = _make_show_and_episode(session, identifier="ep-extra.2500.1")

    detail = _episode_detail(
        slug=episode.slug,
        episode_number="2500.10",
    )

    assert reconcile_episode_identifier_from_dailywire(session, episode, detail) is False
    assert episode.episode_identifier == "ep-extra.2500.1"

    session.close()
    engine.dispose()


def test_unusable_media_cleanup_defaults_to_hourly():
    from config.settings.settings import AppSettings

    settings = AppSettings(timezone="UTC")
    assert settings.new_episode_schedule.cleanup_episodes_stuck_without_media_cron == "0 * * * *"
