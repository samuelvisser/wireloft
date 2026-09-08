from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from unittest.mock import Mock

from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_monitor_reconciles_identifier_and_rekeys_recurring_job(monkeypatch):
    import backend.db.models  # noqa: F401
    from backend.db import Base
    from backend.db.models import Episode, Season, Show
    from backend.types.episode_types import EpisodePublishStatus
    from backend.types.show_types import EpisodeIdentifier, ShowType
    from backend.utils.helpers import generate_uuid
    from dailywire_api.records import DwEpisodeDetailRecord
    from task_manager.tasks.helpers.episodes import events as episode_events
    from task_manager.tasks.workers.monitor_episode_worker import service
    from task_manager.tasks.workers.monitor_episode_worker.scheduling import (
        MONITOR_COMPLETED_EVENT,
        MONITOR_REQUESTED_EVENT,
    )

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)

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

    old_identifier = "ep-extra.2500.1"
    episode = Episode(
        uuid=generate_uuid(),
        type="episode",
        show=show,
        season=season,
        index=2500,
        episode_identifier=old_identifier,
        slug="the-ben-shapiro-show-2500",
        title="BREAKING: Judge Threatens Mistrial",
        duration=3600,
        publish_status=EpisodePublishStatus.LIVE.value,
        metadata_is_final=False,
        sharing_url="https://example.test/episode",
        published_date=datetime.now(timezone.utc).replace(tzinfo=None),
        is_no_show_today=False,
    )
    session.add(episode)
    show.set_meta("ep_id.latest_ep_num", "2500")
    show.set_meta("ep_id.latest_ep_extra_num", "1")
    session.commit()

    published_at = datetime.now(timezone.utc)
    detail = DwEpisodeDetailRecord(
        dw_id="remote-2500",
        slug=episode.slug,
        title=episode.title,
        description=None,
        duration=3600,
        episode_number="2500.00",
        display_episode_number="2500",
        background_image_path=None,
        sharing_url=episode.sharing_url,
        publish_status="LIVE",
        is_downloadable=False,
        available_for=[],
        thumbnail_landscape_path=None,
        thumbnail_portrait_path=None,
        thumbnail_square_path=None,
        published_date=published_at,
        scheduled_date=None,
        audio_url="https://example.test/audio.mp3",
        video_url="https://example.test/video.m3u8",
        delivery_mode="VOD",
        progress=0,
        next_episode_url=None,
        playback_status=None,
    )

    class FakeClient:
        def get_episode_details(self, slug, *, require_member_exclusive):
            assert slug == episode.slug
            assert require_member_exclusive is False
            return detail

    monitor_events = Mock()
    monkeypatch.setattr(service, "MiddlewareClient", FakeClient)
    monkeypatch.setattr(service, "queue_event", monitor_events)
    monkeypatch.setattr(episode_events, "queue_event", Mock())

    result = asyncio.run(
        service.run_monitor_episode_worker(
            session,
            episode_id=episode.id,
            episode_slug=episode.slug,
            show_slug=show.slug,
            season_id=season.id,
            episode_identifier=old_identifier,
            episode_index=episode.index,
        )
    )

    assert result is EpisodePublishStatus.LIVE
    session.expire_all()
    stored = session.get(Episode, episode.id)
    assert stored is not None
    assert stored.episode_identifier == "ep.2500"
    assert show.get_meta("ep_id.latest_ep_extra_num") == "0"

    completed = [
        call.args[2]
        for call in monitor_events.call_args_list
        if call.args[1] == MONITOR_COMPLETED_EVENT
    ]
    requested = [
        call.args[2]
        for call in monitor_events.call_args_list
        if call.args[1] == MONITOR_REQUESTED_EVENT
    ]
    assert len(completed) == 1
    assert completed[0]["episode_identifier"] == old_identifier
    assert len(requested) == 1
    assert requested[0]["episode_identifier"] == "ep.2500"
    assert requested[0]["resource_id"] == episode.id

    session.close()
    engine.dispose()
