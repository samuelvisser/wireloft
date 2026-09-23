from __future__ import annotations

from datetime import datetime, timezone
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


def _show(session: Session):
    from backend.db.models import Show
    from backend.types.show_types import EpisodeIdentifier, ShowType

    item = Show(
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
    session.add(item)
    session.flush()
    return item


def _season(session: Session, show):
    from backend.db.models import Season

    item = Season(show=show, index=1, slug="season-1", name="Season 1")
    session.add(item)
    session.flush()
    return item


def _episode(
    session: Session,
    show,
    season,
    *,
    status: str = "live",
    index: int = 1,
):
    from backend.db.models import Episode

    now = datetime.now(timezone.utc)
    item = Episode(
        uuid=f"episode-{index}-uuid",
        type="episode",
        show=show,
        season=season,
        index=index,
        episode_identifier=f"ep.{index}",
        slug=f"episode-{index}",
        title=f"Episode {index}",
        description="Description",
        duration=1800.0,
        publish_status=status,
        sharing_url=f"https://example.test/episode-{index}",
        went_live_date=now,
        published_date=now if status != "live" else None,
    )
    session.add(item)
    session.flush()
    return item


def _local_profile(session: Session, *, slug: str, preferred_format: str):
    from backend.db.models import LocalMediaProfile

    item = LocalMediaProfile(
        slug=slug,
        name=slug,
        output_template=f"/downloads/{slug}/{{{{ episode_title }}}}.ext",
        preferred_format=preferred_format,
    )
    session.add(item)
    session.flush()
    return item


def _download_profile(session: Session, show, local_profile, *, enabled: bool = True):
    from backend.db.models import PodcastDownloadProfile

    item = PodcastDownloadProfile(
        show=show,
        local_media_profile=local_profile,
        enable_profile=enabled,
        ep_id_type_list=["ep"],
        download_with_countdown=False,
        redownload_final=False,
        download_days_in_past=0,
        download_episode_count=5,
        delete_older_episodes=True,
    )
    session.add(item)
    session.flush()
    return item


def _rss_profile(
    session: Session,
    show,
    *,
    use_dw_stream: bool,
    mode: str = "audio_hls",
    live: bool = True,
    max_items: int = 0,
):
    from backend.db.models import RssStreamProfile

    item = RssStreamProfile(
        show=show,
        enable_profile=True,
        token="token",
        use_downloads=True,
        use_dw_stream=use_dw_stream,
        preferred_format="format_1080p",
        require_exact_match=False,
        ep_id_type_list=["ep"],
        feed_url="https://wireloft.test/feed.xml",
        video_output_mode=mode,
        stream_live_episodes=live,
        live_episode_handoff_ids=[],
        max_items=max_items,
    )
    session.add(item)
    session.flush()
    return item


def _available_hls(session: Session, episode, local_profile, download_profile, path: Path):
    from backend.db.models import EpisodeMediaDownload
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from backend.types.media_types import MediaType
    from dailywire_downloader import hls_asset_marker, hls_asset_root

    path.write_text(
        "#EXTM3U\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=1,RESOLUTION=854x480\n"
        "hls/480p/playlist.m3u8\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=2,RESOLUTION=1280x720\n"
        "hls/720p/playlist.m3u8\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=3,RESOLUTION=1920x1080\n"
        "hls/1080p/playlist.m3u8\n"
    )
    assets = hls_asset_root(path)
    assets.mkdir()
    hls_asset_marker(path).write_text("owned")
    for height in (480, 720, 1080):
        directory = assets / f"{height}p"
        directory.mkdir()
        (directory / "media.ts").write_bytes(b"segment")
        (directory / "playlist.m3u8").write_text(
            "#EXTM3U\n"
            "#EXT-X-VERSION:4\n"
            "#EXTINF:6.0,\n"
            "#EXT-X-BYTERANGE:7@0\n"
            "media.ts\n"
            "#EXT-X-ENDLIST\n"
        )

    item = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=episode.id,
        local_media_profile_id=local_profile.id,
        download_profile_id=download_profile.id,
        file_path=str(path),
        artifact_status=MediaDownloadArtifactStatus.AVAILABLE.value,
        downloaded_bytes=path.stat().st_size,
        downloaded_at=datetime.now(timezone.utc),
        downloaded_publish_status="published_final",
    )
    session.add(item)
    session.flush()
    return item


def test_live_hls_with_dailywire_enabled_is_included(db_session):
    from backend.api.endpoints.feeds.service import get_feed_items

    show = _show(db_session)
    season = _season(db_session, show)
    episode = _episode(db_session, show, season)
    profile = _rss_profile(db_session, show, use_dw_stream=True)

    assert get_feed_items(db_session, profile) == [(episode, None)]


def test_live_hls_without_normal_dailywire_requires_matching_hls_download_profile(
        db_session,
):
    from backend.api.endpoints.feeds.service import get_feed_items

    show = _show(db_session)
    season = _season(db_session, show)
    episode = _episode(db_session, show, season)
    profile = _rss_profile(db_session, show, use_dw_stream=False)

    normal_video = _local_profile(
        db_session,
        slug="video",
        preferred_format="format_1080p",
    )
    _download_profile(db_session, show, normal_video)

    assert get_feed_items(db_session, profile) == []

    hls = _local_profile(
        db_session,
        slug="hls",
        preferred_format="format_hls",
    )
    _download_profile(db_session, show, hls)

    assert get_feed_items(db_session, profile) == [(episode, None)]


def test_live_toggle_has_no_effect_for_non_hls_output_mode(db_session):
    from backend.api.endpoints.feeds.service import get_feed_items

    show = _show(db_session)
    season = _season(db_session, show)
    _episode(db_session, show, season)
    profile = _rss_profile(
        db_session,
        show,
        use_dw_stream=True,
        mode="audio_mp4",
        live=True,
    )

    assert get_feed_items(db_session, profile) == []


def test_live_handoff_keeps_same_remote_hls_url_usable_until_final_hls_exists(
        db_session,
        tmp_path,
):
    from backend.api.endpoints.feeds.service import (
        can_use_dailywire_for_episode,
        get_feed_items,
        remember_live_episode_handoff,
    )

    show = _show(db_session)
    season = _season(db_session, show)
    episode = _episode(db_session, show, season)
    hls = _local_profile(
        db_session,
        slug="hls",
        preferred_format="format_hls",
    )
    download_profile = _download_profile(db_session, show, hls)
    profile = _rss_profile(db_session, show, use_dw_stream=False)

    # The HLS route records this only after a real GET has opened the live stream.
    remember_live_episode_handoff(profile, episode)
    assert profile.live_episode_handoff_ids == [episode.id]

    episode.publish_status = "dw_processing"
    db_session.flush()

    assert get_feed_items(db_session, profile) == [(episode, None)]
    assert can_use_dailywire_for_episode(profile, episode) is True
    assert profile.live_episode_handoff_ids == [episode.id]

    episode.publish_status = "published_final"
    episode.published_date = datetime.now(timezone.utc)
    local = _available_hls(
        db_session,
        episode,
        hls,
        download_profile,
        tmp_path / "episode.m3u8",
    )

    assert get_feed_items(db_session, profile) == [(episode, local)]
    assert profile.live_episode_handoff_ids == []
    assert can_use_dailywire_for_episode(profile, episode) is False


def test_live_handoff_is_not_dropped_just_because_episode_leaves_rss_window(
        db_session,
):
    from backend.api.endpoints.feeds.service import get_feed_items, remember_live_episode_handoff

    show = _show(db_session)
    season = _season(db_session, show)
    live_episode = _episode(db_session, show, season)
    hls = _local_profile(
        db_session,
        slug="hls",
        preferred_format="format_hls",
    )
    _download_profile(db_session, show, hls)
    profile = _rss_profile(
        db_session,
        show,
        use_dw_stream=False,
        max_items=1,
    )

    remember_live_episode_handoff(profile, live_episode)
    live_episode.publish_status = "dw_processing"

    # Add a newer live episode so the original cached RSS item falls outside
    # max_items. Its previously published stable URL must still retain handoff state.
    newer = _episode(db_session, show, season, index=2)
    newer.went_live_date = datetime.now(timezone.utc)
    db_session.flush()

    get_feed_items(db_session, profile)

    assert live_episode.id in profile.live_episode_handoff_ids



def test_live_mp4_endpoint_never_waits_for_full_mp4_preparation(monkeypatch):
    from contextlib import contextmanager
    from types import SimpleNamespace

    from fastapi import HTTPException

    import backend.api.endpoints.feeds.router as feed_router

    profile = SimpleNamespace(
        preferred_format="format_1080p",
        video_output_mode="mp4_hls",
    )
    episode = SimpleNamespace(
        publish_status="live",
        slug="episode-1",
        uuid="episode-uuid",
    )

    class _Session:
        dirty = set()

        def commit(self):
            pass

    @contextmanager
    def fake_db_session():
        yield _Session()

    monkeypatch.setattr(feed_router, "db_session", fake_db_session)
    monkeypatch.setattr(
        feed_router,
        "get_rss_stream_profile_by_token",
        lambda _s, _token: profile,
    )
    monkeypatch.setattr(
        feed_router,
        "get_episode_for_feed",
        lambda _s, _profile, _slug: episode,
    )
    monkeypatch.setattr(
        feed_router,
        "prepare_cached_mp4",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("live MP4 preparation must not start")
        ),
    )

    with pytest.raises(HTTPException, match="HLS enclosure only") as exc:
        feed_router.rss_feed_episode_video_mp4(
            "token",
            "episode-1",
            SimpleNamespace(method="GET"),
        )

    assert exc.value.status_code == 404
