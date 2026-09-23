from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


class _FakeURL:
    def __init__(self, value: str):
        self._value = value

    def __str__(self) -> str:
        return self._value


class _FakeRequest:
    def __init__(self, base_url: str = "https://wireloft.test/", method: str = "GET"):
        self.base_url = _FakeURL(base_url)
        self.method = method


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


def _make_show(session: Session, *, slug: str = "show"):
    from backend.db.models import Show
    from backend.types.show_types import EpisodeIdentifier, ShowType

    show = Show(
        uuid=f"{slug}-uuid",
        slug=slug,
        title="Test Show",
        description="Description",
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


def _make_season(session: Session, show):
    from backend.db.models import Season

    season = Season(show=show, index=1, slug="season-1", name="Season 1")
    session.add(season)
    session.flush()
    return season


def _make_episode(
    session: Session,
    show,
    season,
    *,
    index: int,
    status: str = "published_final",
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
        episode_identifier=f"ep.{index}",
        slug=f"episode-{index}",
        title=f"Episode {index}",
        description="Description",
        duration=1800.0,
        publish_status=status,
        sharing_url=f"https://example.test/episode-{index}",
        published_date=when if status != "live" else None,
        went_live_date=when if status == "live" else None,
    )
    session.add(episode)
    session.flush()
    return episode


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


def _make_available_download(
    session: Session,
    episode,
    profile,
    path: Path,
):
    from backend.db.models import EpisodeMediaDownload
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from backend.types.media_types import MediaType

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"media-data")
    download = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=episode.id,
        local_media_profile_id=profile.id,
        file_path=str(path),
        artifact_status=MediaDownloadArtifactStatus.AVAILABLE.value,
        downloaded_bytes=path.stat().st_size,
        downloaded_at=datetime.now(timezone.utc),
        downloaded_publish_status=episode.publish_status,
    )
    session.add(download)
    session.flush()
    return download


def _make_rss_profile(
    session: Session,
    show,
    *,
    mode: str = "audio_hls",
    preferred_format: str = "format_1080p",
    use_downloads: bool = True,
    use_dw_stream: bool = False,
    max_items: int = 0,
):
    from backend.db.models import RssStreamProfile

    profile = RssStreamProfile(
        show=show,
        enable_profile=True,
        token="token",
        use_downloads=use_downloads,
        use_dw_stream=use_dw_stream,
        preferred_format=preferred_format,
        require_exact_match=False,
        ep_id_type_list=["ep"],
        feed_url="https://wireloft.test/feeds/rss/token/show.xml",
        video_output_mode=mode,
        stream_live_episodes=False,
        live_episode_handoff_ids=[],
        max_items=max_items,
    )
    session.add(profile)
    session.flush()
    return profile


def test_download_only_feed_excludes_episodes_without_relevant_local_media(
        db_session,
        tmp_path,
):
    from backend.api.endpoints.feeds.service import get_feed_items

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    newest = _make_episode(db_session, show, season, index=2)
    older = _make_episode(
        db_session,
        show,
        season,
        index=1,
        when=datetime.now(timezone.utc) - timedelta(days=1),
    )
    video = _make_local_media_profile(
        db_session,
        slug="video",
        preferred_format="format_1080p",
    )
    local = _make_available_download(
        db_session,
        newest,
        video,
        tmp_path / "newest.mp4",
    )
    profile = _make_rss_profile(
        db_session,
        show,
        mode="mp4",
        use_downloads=True,
        use_dw_stream=False,
    )

    items = get_feed_items(db_session, profile)

    assert items == [(newest, local)]
    assert older not in [episode for episode, _ in items]


def test_dailywire_enabled_feed_keeps_undownloaded_episode_with_stable_url(
        db_session,
):
    from backend.api.endpoints.feeds.service import get_feed_items, render_rss_feed

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    episode = _make_episode(db_session, show, season, index=1)
    profile = _make_rss_profile(
        db_session,
        show,
        mode="audio_hls",
        use_downloads=True,
        use_dw_stream=True,
    )

    assert get_feed_items(db_session, profile) == [(episode, None)]

    xml = render_rss_feed(db_session, _FakeRequest(), profile).decode()
    assert (
        "https://wireloft.test/feeds/rss/token/episodes/episode-1/audio.m4a"
        in xml
    )
    assert (
        "https://wireloft.test/feeds/rss/token/episodes/episode-1/video.m3u8"
        in xml
    )
    assert "dailywire" not in xml.lower()


@pytest.mark.parametrize(
    ("mode", "local_kind", "stable_suffixes"),
    [
        ("audio_hls", "hls", ("audio.m4a", "video.m3u8")),
        ("audio_mp4", "mp4", ("audio.m4a", "video.mp4")),
        ("mp4", "mp4", ("video.mp4",)),
        ("mp4_hls", "hls", ("video.mp4", "video.m3u8")),
    ],
)
def test_rss_media_urls_do_not_change_when_download_appears(
        db_session,
        tmp_path,
        mode,
        local_kind,
        stable_suffixes,
):
    from backend.api.endpoints.feeds.service import render_rss_feed
    from backend.utils.artifact_identity import inspect_artifact
    from dailywire_downloader import hls_asset_marker, hls_asset_root

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    episode = _make_episode(db_session, show, season, index=1)
    profile = _make_rss_profile(
        db_session,
        show,
        mode=mode,
        use_downloads=True,
        use_dw_stream=True,
    )

    before = render_rss_feed(db_session, _FakeRequest(), profile).decode()

    if local_kind == "hls":
        local_profile = _make_local_media_profile(
            db_session,
            slug=f"{mode}-hls",
            preferred_format="format_hls",
        )
        master = tmp_path / f"{mode}.m3u8"
        master.write_text(
            "#EXTM3U\n"
            "#EXT-X-STREAM-INF:BANDWIDTH=1,RESOLUTION=854x480\n"
            "hls/480p/playlist.m3u8\n"
            "#EXT-X-STREAM-INF:BANDWIDTH=2,RESOLUTION=1280x720\n"
            "hls/720p/playlist.m3u8\n"
            "#EXT-X-STREAM-INF:BANDWIDTH=3,RESOLUTION=1920x1080\n"
            "hls/1080p/playlist.m3u8\n"
        )
        assets = hls_asset_root(master)
        assets.mkdir()
        hls_asset_marker(master).write_text("owned")
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
        download = _make_available_download(
            db_session,
            episode,
            local_profile,
            master,
        )
        identity = inspect_artifact(master)
        download.artifact_stat_dev = identity.stat_dev
        download.artifact_stat_ino = identity.stat_ino
        download.artifact_size_bytes = identity.size_bytes
        download.artifact_fingerprint = identity.fingerprint
        download.downloaded_bytes = identity.size_bytes
        db_session.flush()
    else:
        local_profile = _make_local_media_profile(
            db_session,
            slug=f"{mode}-video",
            preferred_format="format_1080p",
        )
        _make_available_download(
            db_session,
            episode,
            local_profile,
            tmp_path / f"{mode}.mp4",
        )

    after = render_rss_feed(db_session, _FakeRequest(), profile).decode()

    base = "https://wireloft.test/feeds/rss/token/episodes/episode-1/"
    for suffix in stable_suffixes:
        stable_url = f"{base}{suffix}"
        assert stable_url in before
        assert stable_url in after

    guid = f"<guid isPermaLink=\"false\">{episode.uuid}</guid>"
    assert guid in before
    assert guid in after


def test_max_items_keeps_newest_feed_entries(db_session):
    from backend.api.endpoints.feeds.service import get_feed_items

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    now = datetime.now(timezone.utc)
    newest = _make_episode(db_session, show, season, index=3, when=now)
    second = _make_episode(
        db_session,
        show,
        season,
        index=2,
        when=now - timedelta(hours=1),
    )
    _make_episode(
        db_session,
        show,
        season,
        index=1,
        when=now - timedelta(hours=2),
    )
    profile = _make_rss_profile(
        db_session,
        show,
        mode="mp4",
        use_downloads=False,
        use_dw_stream=True,
        max_items=2,
    )

    assert [episode for episode, _ in get_feed_items(db_session, profile)] == [
        newest,
        second,
    ]


def test_get_dailywire_stream_url_selects_requested_media(
        db_session,
        monkeypatch,
):
    import backend.api.endpoints.feeds.service as service

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    episode = _make_episode(db_session, show, season, index=1)
    profile = _make_rss_profile(
        db_session,
        show,
        use_downloads=False,
        use_dw_stream=True,
    )

    class FakeClient:
        def get_episode_details(self, slug, *, require_member_exclusive):
            assert slug == episode.slug
            assert require_member_exclusive is False
            return SimpleNamespace(
                audio_url="https://media.example/audio.m4a",
                video_url="https://media.example/video.m3u8",
            )

    monkeypatch.setattr(service, "MiddlewareClient", FakeClient)

    assert service.get_dailywire_stream_url(
        profile,
        episode,
        media_kind="audio",
    ) == "https://media.example/audio.m4a"
    assert service.get_dailywire_stream_url(
        profile,
        episode,
        media_kind="video",
    ) == "https://media.example/video.m3u8"


def test_create_stream_profile_generates_plain_stable_feed_url(db_session):
    from backend.api.endpoints.rss_stream_profiles.service import (
        create_stream_profile_rss,
    )
    from backend.api.models.rss_stream_profile import RssStreamProfileAPICreate

    show = _make_show(db_session)
    body = RssStreamProfileAPICreate(
        show_id=show.id,
        enable_profile=True,
        use_downloads=True,
        use_dw_stream=True,
        preferred_format="format_1080p",
        require_exact_match=False,
        video_output_mode="audio_hls",
    )

    created = create_stream_profile_rss(db_session, _FakeRequest(), body)

    assert created.feed_url.startswith("https://wireloft.test/feeds/rss/")
    assert created.feed_url.endswith("/show.xml")
    assert "dwVideoMethod" not in created.feed_url
    assert "?" not in created.feed_url


def test_api_defaults_to_audio_hls_with_live_streaming_off():
    from backend.api.models.rss_stream_profile import RssStreamProfileAPICreate

    profile = RssStreamProfileAPICreate(
        show_id=1,
        enable_profile=True,
        use_downloads=True,
        use_dw_stream=True,
        preferred_format="format_1080p",
        require_exact_match=False,
    )

    assert profile.video_output_mode.value == "audio_hls"
    assert profile.stream_live_episodes is False



def test_stream_profile_rejects_local_hls_as_preferred_format():
    from pydantic import ValidationError

    from backend.api.models.rss_stream_profile import RssStreamProfileAPICreate

    with pytest.raises(ValidationError, match="Local Media Profile download format"):
        RssStreamProfileAPICreate(
            show_id=1,
            enable_profile=True,
            use_downloads=True,
            use_dw_stream=True,
            preferred_format="format_hls",
            require_exact_match=False,
        )


def test_live_streaming_requires_hls_video_output_mode():
    from pydantic import ValidationError

    from backend.api.models.rss_stream_profile import RssStreamProfileAPICreate

    with pytest.raises(ValidationError, match="requires an HLS"):
        RssStreamProfileAPICreate(
            show_id=1,
            enable_profile=True,
            use_downloads=True,
            use_dw_stream=True,
            preferred_format="format_1080p",
            require_exact_match=False,
            video_output_mode="audio_mp4",
            stream_live_episodes=True,
        )



def _make_hls_bundle(path: Path) -> None:
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


def test_download_only_audio_hls_requires_both_advertised_local_sources(
        db_session,
        tmp_path,
):
    from backend.api.endpoints.feeds.service import get_feed_items

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    episode = _make_episode(db_session, show, season, index=1)
    profile = _make_rss_profile(
        db_session,
        show,
        mode="audio_hls",
        use_downloads=True,
        use_dw_stream=False,
    )

    hls_profile = _make_local_media_profile(
        db_session,
        slug="hls",
        preferred_format="format_hls",
    )
    hls_path = tmp_path / "episode.m3u8"
    hls_download = _make_available_download(
        db_session,
        episode,
        hls_profile,
        hls_path,
    )
    _make_hls_bundle(hls_path)
    hls_download.downloaded_bytes = sum(
        item.stat().st_size
        for item in hls_path.with_name(hls_path.name + ".assets").rglob("*")
        if item.is_file()
    )
    db_session.flush()

    assert get_feed_items(db_session, profile) == []

    audio_profile = _make_local_media_profile(
        db_session,
        slug="audio",
        preferred_format="format_audio_only",
    )
    audio_download = _make_available_download(
        db_session,
        episode,
        audio_profile,
        tmp_path / "episode.m4a",
    )

    assert get_feed_items(db_session, profile) == [(episode, audio_download)]


def test_download_only_mp4_hls_requires_both_advertised_video_sources(
        db_session,
        tmp_path,
):
    from backend.api.endpoints.feeds.service import get_feed_items

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    episode = _make_episode(db_session, show, season, index=1)
    profile = _make_rss_profile(
        db_session,
        show,
        mode="mp4_hls",
        use_downloads=True,
        use_dw_stream=False,
    )

    video_profile = _make_local_media_profile(
        db_session,
        slug="video",
        preferred_format="format_1080p",
    )
    mp4_download = _make_available_download(
        db_session,
        episode,
        video_profile,
        tmp_path / "episode.mp4",
    )

    assert get_feed_items(db_session, profile) == []

    hls_profile = _make_local_media_profile(
        db_session,
        slug="hls",
        preferred_format="format_hls",
    )
    hls_path = tmp_path / "episode.m3u8"
    _make_available_download(
        db_session,
        episode,
        hls_profile,
        hls_path,
    )
    _make_hls_bundle(hls_path)

    assert get_feed_items(db_session, profile) == [(episode, mp4_download)]
