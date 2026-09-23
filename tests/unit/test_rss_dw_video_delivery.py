from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest


MASTER_URL = "https://media.example/master.m3u8"


def _master() -> str:
    return """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-STREAM-INF:BANDWIDTH=900000,RESOLUTION=854x480
480.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=1800000,RESOLUTION=1280x720
720.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=3500000,RESOLUTION=1920x1080
1080.m3u8
"""


def _media(height: int) -> str:
    return f"""#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:6
#EXTINF:6.0,
{height}-000.ts
#EXTINF:6.0,
{height}-001.ts
#EXT-X-ENDLIST
"""


class _Response:
    def __init__(self, payload: bytes):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def iter_chunks(self, _size):
        yield self.payload


def test_hls_download_stores_480_720_and_1080_without_transcoding(
        tmp_path,
        monkeypatch,
):
    import dailywire_downloader.hls_bundle as hls_bundle

    playlists = {
        MASTER_URL: _master(),
        "https://media.example/480.m3u8": _media(480),
        "https://media.example/720.m3u8": _media(720),
        "https://media.example/1080.m3u8": _media(1080),
    }

    monkeypatch.setattr(
        hls_bundle,
        "http_get_text",
        lambda url: playlists[url],
    )
    monkeypatch.setattr(
        hls_bundle,
        "http_get",
        lambda url: _Response(f"bytes:{url}".encode()),
    )

    target = tmp_path / "episode.m3u8"
    result = hls_bundle.download_hls_bundle(MASTER_URL, str(target))

    assert result.path == str(target)
    assert result.segments_downloaded == 6

    master = target.read_text()
    assert "hls/480p/playlist.m3u8" in master
    assert "hls/720p/playlist.m3u8" in master
    assert "hls/1080p/playlist.m3u8" in master

    assets = hls_bundle.hls_asset_root(target)
    assert hls_bundle.hls_asset_marker(target).is_file()
    for height in (480, 720, 1080):
        rendition_dir = assets / f"{height}p"
        playlist = (rendition_dir / "playlist.m3u8").read_text()
        assert playlist.count("#EXT-X-BYTERANGE:") == 2
        assert playlist.count("media.ts") == 2
        media_file = rendition_dir / "media.ts"
        assert media_file.is_file()
        assert media_file.read_bytes() == (
            f"bytes:https://media.example/{height}-000.ts".encode()
            + f"bytes:https://media.example/{height}-001.ts".encode()
        )
        assert not list(rendition_dir.glob("segment-*"))


def test_hls_download_requires_all_three_adaptive_renditions(tmp_path, monkeypatch):
    import dailywire_downloader.hls_bundle as hls_bundle
    from dailywire_downloader import MediaUnavailableError

    master_without_480 = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=1800000,RESOLUTION=1280x720
720.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=3500000,RESOLUTION=1920x1080
1080.m3u8
"""
    monkeypatch.setattr(hls_bundle, "http_get_text", lambda _url: master_without_480)

    with pytest.raises(MediaUnavailableError, match="480p, 720p and 1080p"):
        hls_bundle.download_hls_bundle(
            MASTER_URL,
            str(tmp_path / "episode.m3u8"),
        )


def test_hls_download_rejects_live_playlist(tmp_path, monkeypatch):
    import dailywire_downloader.hls_bundle as hls_bundle
    from dailywire_downloader import DownloadError

    playlists = {
        MASTER_URL: _master(),
        "https://media.example/480.m3u8": _media(480).replace("#EXT-X-ENDLIST\n", ""),
        "https://media.example/720.m3u8": _media(720),
        "https://media.example/1080.m3u8": _media(1080),
    }
    monkeypatch.setattr(hls_bundle, "http_get_text", lambda url: playlists[url])

    with pytest.raises(DownloadError, match="live/incomplete"):
        hls_bundle.download_hls_bundle(
            MASTER_URL,
            str(tmp_path / "episode.m3u8"),
        )


def test_hls_cleanup_removes_owned_companion_assets(tmp_path):
    from dailywire_downloader import hls_asset_marker, hls_asset_root
    from task_manager.tasks.helpers.downloads.download_files import (
        remove_download_artifacts,
    )

    master = tmp_path / "episode.m3u8"
    master.write_text("#EXTM3U\n")
    assets = hls_asset_root(master)
    assets.mkdir()
    hls_asset_marker(master).write_text("owned")
    (assets / "segment.ts").write_bytes(b"segment")

    remove_download_artifacts(str(master))

    assert not master.exists()
    assert not assets.exists()


def test_hls_cleanup_preserves_unowned_similarly_named_directory(tmp_path):
    from dailywire_downloader import hls_asset_root
    from task_manager.tasks.helpers.downloads.download_files import (
        remove_download_artifacts,
    )

    master = tmp_path / "episode.m3u8"
    master.write_text("#EXTM3U\n")
    assets = hls_asset_root(master)
    assets.mkdir()
    (assets / "external.txt").write_text("external")

    remove_download_artifacts(str(master))

    assert not master.exists()
    assert assets.is_dir()
    assert (assets / "external.txt").read_text() == "external"


def test_hls_endpoint_falls_back_directly_to_dailywire_without_mp4_preparation(
        monkeypatch,
):
    import backend.api.endpoints.feeds.router as feed_router

    profile = SimpleNamespace(
        preferred_format="format_1080p",
        video_output_mode="audio_hls",
    )
    episode = SimpleNamespace(
        id=10,
        slug="episode-1",
        uuid="episode-uuid",
        publish_status="published_final",
    )

    class _Session:
        dirty = set()

        def commit(self):
            raise AssertionError("ordinary remote fallback must not mutate state")

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
        "get_local_download_for_episode",
        lambda *_args, **_kwargs: None,
    )
    monkeypatch.setattr(
        feed_router,
        "can_use_dailywire_for_episode",
        lambda _profile, _episode: True,
    )
    monkeypatch.setattr(
        feed_router,
        "get_dailywire_stream_url",
        lambda *_args, **_kwargs: "https://media.example/fresh/master.m3u8",
    )
    monkeypatch.setattr(
        feed_router,
        "remember_live_episode_handoff",
        lambda *_args: None,
    )

    request = SimpleNamespace(method="GET")
    response = feed_router.rss_feed_episode_video_hls(
        "token",
        "episode-1",
        request,
    )

    assert response.status_code == 302
    assert response.headers["location"] == "https://media.example/fresh/master.m3u8"



def test_file_watcher_rejects_incomplete_hls_bundle(tmp_path):
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from dailywire_downloader import hls_asset_marker, hls_asset_root
    from task_manager.tasks.workers.file_watcher.service import _size_problem

    master = tmp_path / "episode.m3u8"
    master.write_text("#EXTM3U\n")
    assets = hls_asset_root(master)
    assets.mkdir()
    hls_asset_marker(master).write_text("owned")
    for height in (480, 1080):
        directory = assets / f"{height}p"
        directory.mkdir()
        (directory / "playlist.m3u8").write_text("#EXTM3U\n")

    download = SimpleNamespace(downloaded_bytes=10_000)
    problem = _size_problem(
        download,
        path=str(master),
        size=master.stat().st_size,
        verify_file_size=True,
    )

    assert problem is not None
    assert problem[0] == MediaDownloadArtifactStatus.CORRUPTED
    assert "720p" in problem[1]



def test_compact_hls_bundle_validator_detects_missing_media_file(
        tmp_path,
        monkeypatch,
):
    import dailywire_downloader.hls_bundle as hls_bundle

    playlists = {
        MASTER_URL: _master(),
        "https://media.example/480.m3u8": _media(480),
        "https://media.example/720.m3u8": _media(720),
        "https://media.example/1080.m3u8": _media(1080),
    }
    monkeypatch.setattr(hls_bundle, "http_get_text", lambda url: playlists[url])
    monkeypatch.setattr(
        hls_bundle,
        "http_get",
        lambda url: _Response(f"bytes:{url}".encode()),
    )

    target = tmp_path / "episode.m3u8"
    hls_bundle.download_hls_bundle(MASTER_URL, str(target))
    missing_media = hls_bundle.hls_asset_root(target) / "720p" / "media.ts"
    missing_media.unlink()

    missing = hls_bundle.missing_hls_bundle_files(target)

    assert missing_media.resolve() in missing
