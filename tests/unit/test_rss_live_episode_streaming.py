from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


@pytest.fixture
def db_session():
    import backend.db.models  # noqa: F401
    from backend.db import Base

    engine = create_engine("sqlite+pysqlite:///:memory:")
    session = Session(engine)
    Base.metadata.create_all(engine)
    yield session
    session.close()
    engine.dispose()


def _make_show(session: Session):
    from backend.db.models import Show
    from backend.types.show_types import EpisodeIdentifier, ShowType

    show = Show(
        uuid="show-uuid",
        slug="show",
        title="Show",
        description="Description",
        sharing_url="https://example.test/show",
        membership_level="FREE",
        type=ShowType.PODCAST.value,
        episode_identifier=EpisodeIdentifier.NUMBERED.value,
        author_name="Host",
        author_slug="host",
    )
    session.add(show)
    session.flush()
    return show


def _make_season(session: Session, show, *, index: int = 1):
    from backend.db.models import Season

    season = Season(
        show=show,
        index=index,
        slug=f"season-{index}",
        name=f"Season {index}",
    )
    session.add(season)
    session.flush()
    return season


def _make_episode(
        session: Session,
        show,
        season,
        *,
        index: int,
        episode_type: str = "ep",
        status: str = "live",
        when: datetime | None = None,
):
    from backend.db.models import Episode

    when = when or datetime.now(timezone.utc)
    episode = Episode(
        uuid=f"episode-{index}-uuid",
        type="episode",
        show=show,
        season=season,
        index=index,
        episode_identifier=f"{episode_type}.{index}",
        slug=f"{episode_type}-{index}",
        title=f"Episode {index}",
        description="Description",
        duration=1800.0,
        publish_status=status,
        sharing_url=f"https://example.test/{episode_type}-{index}",
        went_live_date=when if status == "live" else None,
        published_date=when if status != "live" else None,
    )
    session.add(episode)
    session.flush()
    return episode


def _make_rss_profile(
        session: Session,
        show,
        *,
        use_downloads: bool,
        use_dw_stream: bool,
        stream_live_episodes: bool,
        episode_types: list[str] | None = None,
        max_items: int = 0,
        dw_video_method: str = "stream_hls_download_m4a",
):
    from backend.db.models import RssStreamProfile

    profile = RssStreamProfile(
        show=show,
        enable_profile=True,
        token=f"token-{use_downloads}-{use_dw_stream}-{stream_live_episodes}",
        use_downloads=use_downloads,
        use_dw_stream=use_dw_stream,
        preferred_format="format_1080p",
        require_exact_match=False,
        ep_id_type_list=episode_types or ["ep"],
        feed_url="https://wireloft.test/feed.xml",
        dw_video_method=dw_video_method,
        max_items=max_items,
        stream_live_episodes=stream_live_episodes,
        live_episode_handoff_ids=[],
    )
    session.add(profile)
    session.flush()
    return profile


def _make_local_media_profile(
        session: Session,
        *,
        slug: str,
        preferred_format: str,
):
    from backend.db.models import LocalMediaProfile

    profile = LocalMediaProfile(
        slug=slug,
        name=slug,
        output_template=f"/downloads/{slug}/{{{{ episode_title }}}}.ext",
        preferred_format=preferred_format,
    )
    session.add(profile)
    session.flush()
    return profile


def _make_download_profile(
        session: Session,
        show,
        local_media_profile,
        *,
        episode_types: list[str],
        enabled: bool = True,
):
    from backend.db.models import PodcastDownloadProfile

    profile = PodcastDownloadProfile(
        show=show,
        local_media_profile=local_media_profile,
        enable_profile=enabled,
        ep_id_type_list=episode_types,
        download_with_countdown=False,
        redownload_final=False,
        download_days_in_past=0,
        download_episode_count=0,
        delete_older_episodes=False,
    )
    session.add(profile)
    session.flush()
    return profile


def _make_available_download(
        session: Session,
        episode,
        local_media_profile,
        download_profile,
        file_path: Path,
):
    from backend.db.models import EpisodeMediaDownload
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from backend.types.media_types import MediaType

    file_path.write_bytes(b"video")
    download = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=episode.id,
        local_media_profile_id=local_media_profile.id,
        download_profile_id=download_profile.id,
        file_path=str(file_path),
        artifact_status=MediaDownloadArtifactStatus.AVAILABLE.value,
        downloaded_bytes=file_path.stat().st_size,
        downloaded_at=datetime.now(timezone.utc),
        downloaded_publish_status=episode.publish_status,
    )
    session.add(download)
    session.flush()
    return download


def test_api_defaults_live_episode_streaming_off():
    from backend.api.models.rss_stream_profile import RssStreamProfileAPICreate

    profile = RssStreamProfileAPICreate(
        show_id=1,
        enable_profile=True,
        use_downloads=True,
        use_dw_stream=False,
        preferred_format="format_1080p",
        require_exact_match=False,
    )

    assert profile.stream_live_episodes is False


def test_api_read_does_not_expose_internal_live_handoff_state(db_session: Session):
    from backend.api.models.rss_stream_profile import RssStreamProfileAPIRead

    show = _make_show(db_session)
    profile = _make_rss_profile(
        db_session,
        show,
        use_downloads=True,
        use_dw_stream=False,
        stream_live_episodes=True,
    )
    profile.live_episode_handoff_ids = [123]
    db_session.flush()

    payload = RssStreamProfileAPIRead.model_validate(profile).model_dump()

    assert payload["stream_live_episodes"] is True
    assert "live_episode_handoff_ids" not in payload


def test_profile_update_clears_handoff_when_live_continuity_is_disabled(
        db_session: Session,
):
    from backend.api.endpoints.rss_stream_profiles.service import (
        update_stream_profile_rss,
    )
    from backend.api.models.rss_stream_profile import RssStreamProfileAPIUpdate

    show = _make_show(db_session)
    profile = _make_rss_profile(
        db_session,
        show,
        use_downloads=True,
        use_dw_stream=False,
        stream_live_episodes=True,
    )
    profile.live_episode_handoff_ids = [111, 222]
    db_session.flush()

    body = RssStreamProfileAPIUpdate(
        enable_profile=True,
        use_downloads=True,
        use_dw_stream=False,
        preferred_format="format_1080p",
        require_exact_match=False,
        ep_id_type_list=["ep"],
        dw_video_method="stream_hls_download_m4a",
        max_items=0,
        stream_live_episodes=False,
        feed_url=profile.feed_url,
    )
    updated = update_stream_profile_rss(db_session, profile.id, body)

    assert updated.stream_live_episodes is False
    assert profile.live_episode_handoff_ids == []


def test_profile_update_preserves_handoff_while_continuity_remains_enabled(
        db_session: Session,
):
    from backend.api.endpoints.rss_stream_profiles.service import (
        update_stream_profile_rss,
    )
    from backend.api.models.rss_stream_profile import RssStreamProfileAPIUpdate

    show = _make_show(db_session)
    profile = _make_rss_profile(
        db_session,
        show,
        use_downloads=True,
        use_dw_stream=False,
        stream_live_episodes=True,
    )
    profile.live_episode_handoff_ids = [111]
    db_session.flush()

    body = RssStreamProfileAPIUpdate(
        enable_profile=True,
        use_downloads=True,
        use_dw_stream=False,
        preferred_format="format_1080p",
        require_exact_match=False,
        ep_id_type_list=["ep"],
        dw_video_method="stream_hls_download_m4a",
        max_items=10,
        stream_live_episodes=True,
        feed_url=profile.feed_url,
    )
    update_stream_profile_rss(db_session, profile.id, body)

    assert profile.live_episode_handoff_ids == [111]


def test_live_episode_requires_setting_even_when_dailywire_streaming_is_enabled(
        db_session: Session,
):
    from backend.api.endpoints.feeds.service import get_feed_items

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    episode = _make_episode(db_session, show, season, index=1)
    disabled = _make_rss_profile(
        db_session,
        show,
        use_downloads=False,
        use_dw_stream=True,
        stream_live_episodes=False,
    )

    assert get_feed_items(db_session, disabled) == []

    disabled.stream_live_episodes = True
    items = get_feed_items(db_session, disabled)
    assert items == [(episode, None)]


def test_live_episode_must_match_stream_profile_episode_types(db_session: Session):
    from backend.api.endpoints.feeds.service import get_feed_items

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    _make_episode(
        db_session,
        show,
        season,
        index=1,
        episode_type="aux",
    )
    profile = _make_rss_profile(
        db_session,
        show,
        use_downloads=False,
        use_dw_stream=True,
        stream_live_episodes=True,
        episode_types=["ep"],
    )

    assert get_feed_items(db_session, profile) == []


def test_download_only_live_stream_requires_matching_video_download_profile(
        db_session: Session,
):
    from backend.api.endpoints.feeds.service import get_feed_items

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    episode = _make_episode(db_session, show, season, index=1)
    profile = _make_rss_profile(
        db_session,
        show,
        use_downloads=True,
        use_dw_stream=False,
        stream_live_episodes=True,
    )

    assert get_feed_items(db_session, profile) == []

    audio = _make_local_media_profile(
        db_session,
        slug="audio",
        preferred_format="format_audio_only",
    )
    _make_download_profile(
        db_session,
        show,
        audio,
        episode_types=["ep"],
    )
    assert get_feed_items(db_session, profile) == []

    video = _make_local_media_profile(
        db_session,
        slug="video",
        preferred_format="format_720p",
    )
    _make_download_profile(
        db_session,
        show,
        video,
        episode_types=["aux"],
    )
    assert get_feed_items(db_session, profile) == []

    matching = _make_download_profile(
        db_session,
        show,
        video,
        episode_types=["ep"],
    )
    items = get_feed_items(db_session, profile)

    assert items == [(episode, None)]
    assert profile.live_episode_handoff_ids == []
    assert matching.enable_profile is True


def test_live_coverage_honors_stream_profile_exact_match(
        db_session: Session,
):
    from backend.api.endpoints.feeds.service import get_feed_items

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    episode = _make_episode(db_session, show, season, index=1)
    video = _make_local_media_profile(
        db_session,
        slug="video-720",
        preferred_format="format_720p",
    )
    _make_download_profile(
        db_session,
        show,
        video,
        episode_types=["ep"],
    )
    profile = _make_rss_profile(
        db_session,
        show,
        use_downloads=True,
        use_dw_stream=False,
        stream_live_episodes=True,
    )
    profile.require_exact_match = True
    db_session.flush()

    assert get_feed_items(db_session, profile) == []

    profile.require_exact_match = False
    db_session.flush()
    assert get_feed_items(db_session, profile) == [(episode, None)]


def test_disabled_video_download_profile_does_not_enable_live_stream(
        db_session: Session,
):
    from backend.api.endpoints.feeds.service import get_feed_items

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    _make_episode(db_session, show, season, index=1)
    profile = _make_rss_profile(
        db_session,
        show,
        use_downloads=True,
        use_dw_stream=False,
        stream_live_episodes=True,
    )
    video = _make_local_media_profile(
        db_session,
        slug="video",
        preferred_format="format_1080p",
    )
    _make_download_profile(
        db_session,
        show,
        video,
        episode_types=["ep"],
        enabled=False,
    )

    assert get_feed_items(db_session, profile) == []
    assert profile.live_episode_handoff_ids == []


def test_live_episode_prefers_live_hls_over_existing_local_artifact(
        db_session: Session,
        tmp_path: Path,
        monkeypatch,
):
    import backend.api.endpoints.feeds.service as feed_service

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    episode = _make_episode(db_session, show, season, index=1)
    video = _make_local_media_profile(
        db_session,
        slug="video",
        preferred_format="format_1080p",
    )
    download_profile = _make_download_profile(
        db_session,
        show,
        video,
        episode_types=["ep"],
    )
    _make_available_download(
        db_session,
        episode,
        video,
        download_profile,
        tmp_path / "episode.mp4",
    )
    profile = _make_rss_profile(
        db_session,
        show,
        use_downloads=True,
        use_dw_stream=False,
        stream_live_episodes=True,
    )
    monkeypatch.setattr(
        feed_service,
        "resolve_media_download_file",
        lambda _session, download, **_kwargs: Path(download.file_path),
    )

    assert feed_service.get_feed_items(db_session, profile) == [(episode, None)]
    assert profile.live_episode_handoff_ids == []


def test_live_handoff_bridges_processing_until_first_local_video(
        db_session: Session,
        tmp_path: Path,
        monkeypatch,
):
    import backend.api.endpoints.feeds.service as feed_service

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    episode = _make_episode(db_session, show, season, index=1)
    video = _make_local_media_profile(
        db_session,
        slug="video",
        preferred_format="format_1080p",
    )
    download_profile = _make_download_profile(
        db_session,
        show,
        video,
        episode_types=["ep"],
    )
    profile = _make_rss_profile(
        db_session,
        show,
        use_downloads=True,
        use_dw_stream=False,
        stream_live_episodes=True,
    )
    monkeypatch.setattr(
        feed_service,
        "resolve_media_download_file",
        lambda _session, download, **_kwargs: Path(download.file_path),
    )

    class FakeClient:
        def get_episode_details(self, slug, *, require_member_exclusive):
            assert slug == episode.slug
            return type("Detail", (), {
                "video_url": "https://media.example/live.m3u8",
                "audio_url": "https://media.example/live.m4a",
            })()

    monkeypatch.setattr(feed_service, "MiddlewareClient", FakeClient)
    request = type("Request", (), {"base_url": "https://wireloft.test/"})()
    feed_service.render_rss_feed(db_session, request, profile)
    assert profile.live_episode_handoff_ids == [episode.id]

    episode.publish_status = "dw_processing"
    db_session.flush()

    assert feed_service.get_feed_items(db_session, profile) == [(episode, None)]
    resolved_episode, download = feed_service.get_media_for_episode(
        db_session,
        profile,
        episode.slug,
    )
    assert resolved_episode.id == episode.id
    assert download is None
    assert profile.live_episode_handoff_ids == [episode.id]

    local_download = _make_available_download(
        db_session,
        episode,
        video,
        download_profile,
        tmp_path / "final.mp4",
    )
    assert feed_service.get_feed_items(db_session, profile) == [
        (episode, local_download)
    ]
    assert profile.live_episode_handoff_ids == []

    db_session.delete(local_download)
    db_session.flush()
    assert feed_service.get_feed_items(db_session, profile) == []


def test_non_live_undownloaded_episode_never_gets_temporary_dailywire_fallback(
        db_session: Session,
):
    from backend.api.endpoints.feeds.service import get_feed_items

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    _make_episode(
        db_session,
        show,
        season,
        index=1,
        status="published_final",
    )
    video = _make_local_media_profile(
        db_session,
        slug="video",
        preferred_format="format_1080p",
    )
    _make_download_profile(
        db_session,
        show,
        video,
        episode_types=["ep"],
    )
    profile = _make_rss_profile(
        db_session,
        show,
        use_downloads=True,
        use_dw_stream=False,
        stream_live_episodes=True,
    )

    assert get_feed_items(db_session, profile) == []
    assert profile.live_episode_handoff_ids == []


def test_historical_live_date_does_not_recreate_dailywire_fallback(
        db_session: Session,
):
    from backend.api.endpoints.feeds.service import get_feed_items

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    episode = _make_episode(
        db_session,
        show,
        season,
        index=1,
        status="published_final",
    )
    episode.went_live_date = datetime.now(timezone.utc) - timedelta(hours=1)
    video = _make_local_media_profile(
        db_session,
        slug="video",
        preferred_format="format_1080p",
    )
    _make_download_profile(
        db_session,
        show,
        video,
        episode_types=["ep"],
    )
    profile = _make_rss_profile(
        db_session,
        show,
        use_downloads=True,
        use_dw_stream=False,
        stream_live_episodes=True,
    )
    db_session.flush()

    assert get_feed_items(db_session, profile) == []
    assert profile.live_episode_handoff_ids == []


def test_series_download_profile_must_cover_live_episode_season(
        db_session: Session,
):
    from backend.api.endpoints.feeds.service import get_feed_items
    from backend.db.models import SeriesDownloadProfile

    show = _make_show(db_session)
    current_season = _make_season(db_session, show, index=1)
    other_season = _make_season(db_session, show, index=2)
    episode = _make_episode(db_session, show, current_season, index=1)
    video = _make_local_media_profile(
        db_session,
        slug="video",
        preferred_format="format_1080p",
    )
    download_profile = SeriesDownloadProfile(
        show=show,
        local_media_profile=video,
        enable_profile=True,
        ep_id_type_list=["ep"],
        include_upcoming_seasons=False,
    )
    download_profile.seasons = [other_season]
    db_session.add(download_profile)
    db_session.flush()

    profile = _make_rss_profile(
        db_session,
        show,
        use_downloads=True,
        use_dw_stream=False,
        stream_live_episodes=True,
    )

    assert get_feed_items(db_session, profile) == []

    download_profile.seasons = [current_season]
    db_session.flush()
    assert get_feed_items(db_session, profile) == [(episode, None)]


def test_series_upcoming_season_can_cover_live_episode(
        db_session: Session,
):
    from backend.api.endpoints.feeds.service import get_feed_items
    from backend.db.models import SeriesDownloadProfile

    show = _make_show(db_session)
    selected_season = _make_season(db_session, show, index=1)
    upcoming_season = _make_season(db_session, show, index=2)
    episode = _make_episode(db_session, show, upcoming_season, index=1)
    video = _make_local_media_profile(
        db_session,
        slug="video",
        preferred_format="format_1080p",
    )
    download_profile = SeriesDownloadProfile(
        show=show,
        local_media_profile=video,
        enable_profile=True,
        ep_id_type_list=["ep"],
        include_upcoming_seasons=True,
    )
    download_profile.seasons = [selected_season]
    db_session.add(download_profile)
    db_session.flush()

    profile = _make_rss_profile(
        db_session,
        show,
        use_downloads=True,
        use_dw_stream=False,
        stream_live_episodes=True,
    )

    assert get_feed_items(db_session, profile) == [(episode, None)]


def test_live_handoff_is_only_created_for_live_items_emitted_by_max_items(
        db_session: Session,
        monkeypatch,
):
    show = _make_show(db_session)
    season = _make_season(db_session, show)
    now = datetime.now(timezone.utc)
    older = _make_episode(
        db_session,
        show,
        season,
        index=1,
        when=now - timedelta(minutes=10),
    )
    newer = _make_episode(
        db_session,
        show,
        season,
        index=2,
        when=now,
    )
    video = _make_local_media_profile(
        db_session,
        slug="video",
        preferred_format="format_1080p",
    )
    _make_download_profile(
        db_session,
        show,
        video,
        episode_types=["ep"],
    )
    profile = _make_rss_profile(
        db_session,
        show,
        use_downloads=True,
        use_dw_stream=False,
        stream_live_episodes=True,
        max_items=1,
    )

    import backend.api.endpoints.feeds.service as feed_service

    class FakeClient:
        def get_episode_details(self, slug, *, require_member_exclusive):
            return type("Detail", (), {
                "video_url": f"https://media.example/{slug}.m3u8",
                "audio_url": f"https://media.example/{slug}.m4a",
            })()

    monkeypatch.setattr(feed_service, "MiddlewareClient", FakeClient)
    request = type("Request", (), {"base_url": "https://wireloft.test/"})()
    feed_service.render_rss_feed(db_session, request, profile)

    assert profile.live_episode_handoff_ids == [newer.id]
    assert older.id not in profile.live_episode_handoff_ids


def test_live_episode_is_rendered_from_dailywire_even_when_normal_dw_streaming_is_off(
        db_session: Session,
        monkeypatch,
):
    import backend.api.endpoints.feeds.service as feed_service

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    episode = _make_episode(db_session, show, season, index=1)
    video = _make_local_media_profile(
        db_session,
        slug="video",
        preferred_format="format_1080p",
    )
    _make_download_profile(
        db_session,
        show,
        video,
        episode_types=["ep"],
    )
    profile = _make_rss_profile(
        db_session,
        show,
        use_downloads=True,
        use_dw_stream=False,
        stream_live_episodes=True,
    )

    class FakeClient:
        def get_episode_details(self, slug, *, require_member_exclusive):
            assert slug == episode.slug
            return type("Detail", (), {
                "video_url": "https://media.example/live.m3u8",
                "audio_url": "https://media.example/live.m4a",
            })()

    monkeypatch.setattr(feed_service, "MiddlewareClient", FakeClient)

    request = type("Request", (), {"base_url": "https://wireloft.test/"})()
    xml = feed_service.render_rss_feed(db_session, request, profile).decode("utf-8")

    assert "https://media.example/live.m3u8" in xml
    assert (
        f'<guid isPermaLink="false">{episode.uuid}</guid>'
        in xml
    )
    assert profile.live_episode_handoff_ids == [episode.id]


def test_existing_live_handoff_survives_failed_live_refresh(
        db_session: Session,
        monkeypatch,
):
    import backend.api.endpoints.feeds.service as feed_service

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    episode = _make_episode(db_session, show, season, index=1)
    video = _make_local_media_profile(
        db_session,
        slug="video",
        preferred_format="format_1080p",
    )
    _make_download_profile(
        db_session,
        show,
        video,
        episode_types=["ep"],
    )
    profile = _make_rss_profile(
        db_session,
        show,
        use_downloads=True,
        use_dw_stream=False,
        stream_live_episodes=True,
    )
    profile.live_episode_handoff_ids = [episode.id]

    class FakeClient:
        def get_episode_details(self, slug, *, require_member_exclusive):
            return type("Detail", (), {
                "video_url": None,
                "audio_url": "https://media.example/live.m4a",
            })()

    monkeypatch.setattr(feed_service, "MiddlewareClient", FakeClient)
    request = type("Request", (), {"base_url": "https://wireloft.test/"})()
    feed_service.render_rss_feed(db_session, request, profile)

    assert profile.live_episode_handoff_ids == [episode.id]


def test_failed_live_hls_resolution_does_not_start_handoff(
        db_session: Session,
        monkeypatch,
):
    import backend.api.endpoints.feeds.service as feed_service

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    _make_episode(db_session, show, season, index=1)
    video = _make_local_media_profile(
        db_session,
        slug="video",
        preferred_format="format_1080p",
    )
    _make_download_profile(
        db_session,
        show,
        video,
        episode_types=["ep"],
    )
    profile = _make_rss_profile(
        db_session,
        show,
        use_downloads=True,
        use_dw_stream=False,
        stream_live_episodes=True,
    )

    class FakeClient:
        def get_episode_details(self, slug, *, require_member_exclusive):
            return type("Detail", (), {
                "video_url": None,
                "audio_url": "https://media.example/live.m4a",
            })()

    monkeypatch.setattr(feed_service, "MiddlewareClient", FakeClient)
    request = type("Request", (), {"base_url": "https://wireloft.test/"})()
    xml = feed_service.render_rss_feed(db_session, request, profile).decode("utf-8")

    assert profile.live_episode_handoff_ids == []
    assert "<title>Episode 1</title>" not in xml


def test_non_hls_video_method_never_enables_live_streaming(db_session: Session):
    from backend.api.endpoints.feeds.service import get_feed_items

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    _make_episode(db_session, show, season, index=1)
    profile = _make_rss_profile(
        db_session,
        show,
        use_downloads=False,
        use_dw_stream=True,
        stream_live_episodes=True,
        dw_video_method="stream_download_mp4",
    )

    assert get_feed_items(db_session, profile) == []
