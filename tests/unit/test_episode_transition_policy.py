from datetime import datetime, timedelta, timezone
from types import SimpleNamespace


def _detail(
    *,
    publish_status="PUBLISHED",
    downloadable=True,
    duration=3600,
    slug="episode",
    video_url="https://example.test/video.m3u8",
):
    from dailywire_api.records import DwEpisodeDetailRecord, DwEpisodeRecord

    record = DwEpisodeRecord(
        dw_id="remote-episode",
        slug=slug,
        title="Episode",
        description=None,
        duration=duration,
        episode_number="10.00",
        display_episode_number="10",
        background_image_path=None,
        sharing_url="https://example.test/episode",
        publish_status=publish_status,
        is_downloadable=downloadable,
        available_for=[],
        thumbnail_landscape_path=None,
        thumbnail_portrait_path=None,
        thumbnail_square_path=None,
        published_date=datetime.now(timezone.utc) - timedelta(minutes=30),
        scheduled_date=None,
    )
    return DwEpisodeDetailRecord(
        **record.model_dump(mode="python", by_alias=False),
        audio_url="https://example.test/audio.mp3",
        video_url=video_url,
        delivery_mode="VOD",
        progress=0,
        next_episode_url=None,
        playback_status=None,
    )


def _settings():
    return SimpleNamespace(
        episode_status_timing=SimpleNamespace(
            dw_processing_max_minutes=60,
            published_final_after_minutes=180,
        )
    )


def test_final_episode_does_not_regress_to_inferred_countdown(monkeypatch):
    from backend.types.episode_types import EpisodePublishStatus
    from task_manager.tasks.helpers.episodes import status

    monkeypatch.setattr(status, "get_settings", _settings)
    monkeypatch.setattr(status, "get_vod_info", lambda _url: SimpleNamespace(seconds=3600))
    detail = _detail(downloadable=False)
    observed = status.observe_episode_detail(detail)

    resolved = status.resolve_episode_status(
        detail,
        current_status=EpisodePublishStatus.PUBLISHED_FINAL,
        snapshot=observed,
    )

    assert observed.status is EpisodePublishStatus.PUBLISHED_WITH_COUNTDOWN
    assert resolved.status is EpisodePublishStatus.PUBLISHED_FINAL


def test_authoritative_live_can_move_final_episode_back_to_pending():
    from backend.types.episode_types import EpisodePublishStatus
    from task_manager.tasks.helpers.episodes import status

    detail = _detail(publish_status="LIVE", downloadable=False)
    observed = status.observe_episode_detail(detail)
    resolved = status.resolve_episode_status(
        detail,
        current_status=EpisodePublishStatus.PUBLISHED_FINAL,
        snapshot=observed,
    )

    assert observed.status is EpisodePublishStatus.LIVE
    assert resolved.status is EpisodePublishStatus.LIVE


def test_unusable_remote_snapshot_can_move_final_episode_to_quarantine(monkeypatch):
    from backend.types.episode_types import EpisodePublishStatus
    from task_manager.tasks.helpers.episodes import status

    monkeypatch.setattr(status, "get_settings", _settings)
    detail = _detail(video_url=None)
    observed = status.observe_episode_detail(detail)
    resolved = status.resolve_episode_status(
        detail,
        current_status=EpisodePublishStatus.PUBLISHED_FINAL,
        snapshot=observed,
    )

    assert observed.status is EpisodePublishStatus.NO_USABLE_MEDIA
    assert resolved.status is EpisodePublishStatus.NO_USABLE_MEDIA
