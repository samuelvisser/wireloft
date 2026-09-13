from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from xml.etree.ElementTree import Element

import pytest


STABLE_HLS_CASES = [
    ("experiment_hls_redirect_302", "video.m3u8", "application/x-mpegURL"),
    (
        "experiment_hls_https_redirect_302",
        "video-https.m3u8",
        "application/x-mpegURL",
    ),
    (
        "experiment_hls_cached_redirect_302",
        "video-cached-302.m3u8",
        "application/x-mpegURL",
    ),
    (
        "experiment_hls_head_200_get_302",
        "video-head200.m3u8",
        "application/x-mpegURL",
    ),
    (
        "experiment_hls_redirect_302_headers",
        "video-302-headers.m3u8",
        "application/x-mpegURL",
    ),
    (
        "experiment_hls_prewarmed_raw",
        "video-prewarmed-raw.m3u8",
        "application/x-mpegURL",
    ),
    (
        "experiment_hls_prewarmed_absolute",
        "video-prewarmed-absolute.m3u8",
        "application/x-mpegURL",
    ),
    ("experiment_hls_redirect_307", "video-307.m3u8", "application/x-mpegURL"),
    ("experiment_hls_redirect_308", "video-308.m3u8", "application/x-mpegURL"),
    ("experiment_hls_proxy_video_x", "video-proxy.m3u8", "application/x-mpegURL"),
    ("experiment_hls_proxy_master_x", "master.m3u8", "application/x-mpegURL"),
    ("experiment_hls_proxy_index_x", "index.m3u8", "application/x-mpegURL"),
    (
        "experiment_hls_proxy_video_apple",
        "video-proxy-apple.m3u8",
        "application/vnd.apple.mpegurl",
    ),
    (
        "experiment_hls_proxy_video_generic",
        "video-proxy-generic.m3u8",
        "application/mpegurl",
    ),
    ("experiment_hls_prepared_ts", "prepared/video.m3u8", "application/x-mpegURL"),
]


def _episode(*, slug: str = "episode-1", uuid: str = "episode-uuid"):
    return SimpleNamespace(
        title="Episode 1",
        uuid=uuid,
        slug=slug,
        description=None,
        published_date=datetime(2026, 9, 3, tzinfo=timezone.utc),
        went_live_date=None,
        created_at=datetime(2026, 9, 3, tzinfo=timezone.utc),
        duration=1800.0,
        thumbnail_landscape_path=None,
        thumbnail_square_path=None,
        thumbnail_portrait_path=None,
    )


def _children(parent: Element, tag: str) -> list[Element]:
    return [child for child in parent if child.tag == tag]


@pytest.mark.parametrize("method, endpoint, mime_type", STABLE_HLS_CASES)
def test_stable_hls_experiments_emit_wireloft_m3u8_urls(
        method: str,
        endpoint: str,
        mime_type: str,
):
    from backend.api.endpoints.feeds.service import _append_item

    channel = Element("channel")
    _append_item(
        channel,
        media_base_url="https://wireloft.example/feeds/rss/token",
        episode=_episode(),
        download=None,
        preferred_format="format_1080p",
        dw_video_method=method,
        dw_video_url=None,
        experiment_guid_scope="token",
    )

    item = channel.find("item")
    assert item is not None
    enclosure = item.find("enclosure")
    assert enclosure is not None
    assert enclosure.attrib == {
        "url": "https://wireloft.example/feeds/rss/token/episodes/episode-1/audio.m4a",
        "length": "0",
        "type": "audio/mp4",
    }

    alternates = _children(item, "podcast:alternateEnclosure")
    assert len(alternates) == 1
    assert alternates[0].attrib["type"] == mime_type
    sources = _children(alternates[0], "podcast:source")
    assert len(sources) == 1
    assert sources[0].attrib["uri"] == (
        f"https://wireloft.example/feeds/rss/token/episodes/episode-1/{endpoint}"
    )
    assert sources[0].attrib["uri"].endswith(".m3u8")
    assert item.find("guid").text == f"episode-uuid:{method}:token"


def test_https_experiment_upgrades_hls_source_when_feed_base_is_http():
    from backend.api.endpoints.feeds.service import _append_item

    channel = Element("channel")
    _append_item(
        channel,
        media_base_url="http://wireloft.example/feeds/rss/token",
        episode=_episode(),
        download=None,
        preferred_format="format_1080p",
        dw_video_method="experiment_hls_https_redirect_302",
        experiment_guid_scope="token",
    )

    item = channel.find("item")
    assert item is not None
    enclosure = item.find("enclosure")
    assert enclosure is not None
    assert enclosure.attrib["url"].startswith("http://wireloft.example/")

    alternate = _children(item, "podcast:alternateEnclosure")[0]
    source = _children(alternate, "podcast:source")[0]
    assert source.attrib["uri"] == (
        "https://wireloft.example/feeds/rss/token/episodes/episode-1/"
        "video-https.m3u8"
    )


def test_embedded_hls_control_still_uses_signed_dailywire_url():
    from backend.api.endpoints.feeds.service import _append_item

    signed_url = "https://stream.dailywire.example/master.m3u8?token=fresh"
    channel = Element("channel")
    _append_item(
        channel,
        media_base_url="https://wireloft.example/feeds/rss/token",
        episode=_episode(),
        download=None,
        preferred_format="format_1080p",
        dw_video_method="stream_hls_download_m4a",
        dw_video_url=signed_url,
    )

    item = channel.find("item")
    alternate = _children(item, "podcast:alternateEnclosure")[0]
    source = _children(alternate, "podcast:source")[0]
    assert source.attrib["uri"] == signed_url


def test_remote_audio_enclosure_has_m4a_extension():
    from backend.api.endpoints.feeds.service import _append_item

    channel = Element("channel")
    _append_item(
        channel,
        media_base_url="https://wireloft.example/feeds/rss/token",
        episode=_episode(),
        download=None,
        preferred_format="format_audio_only",
    )

    enclosure = channel.find("item/enclosure")
    assert enclosure is not None
    assert enclosure.attrib["url"].endswith("/audio.m4a")
    assert enclosure.attrib["type"] == "audio/mp4"


def test_download_enclosure_uses_real_file_extension(tmp_path: Path):
    from backend.api.endpoints.feeds.service import _append_item

    file_path = tmp_path / "episode.m4a"
    file_path.write_bytes(b"audio")
    download = SimpleNamespace(
        file_path=str(file_path),
        downloaded_bytes=0,
        local_media_profile=SimpleNamespace(preferred_format="format_audio_only"),
    )

    channel = Element("channel")
    _append_item(
        channel,
        media_base_url="https://wireloft.example/feeds/rss/token",
        episode=_episode(),
        download=download,
        preferred_format="format_audio_only",
    )

    enclosure = channel.find("item/enclosure")
    assert enclosure is not None
    assert enclosure.attrib["url"].endswith("/download.m4a")


@pytest.mark.parametrize("status_code", [302, 307, 308])
def test_redirect_experiments_preserve_requested_status(status_code: int):
    from backend.api.endpoints.feeds.router import _temporary_stream_redirect

    response = _temporary_stream_redirect(
        "https://stream.example/master.m3u8?token=fresh",
        head_only=True,
        status_code=status_code,
    )
    assert response.status_code == status_code
    assert response.headers["location"].startswith("https://stream.example/")
    assert response.headers["cache-control"] == "no-store, no-cache, must-revalidate"


def test_redirect_can_advertise_hls_headers():
    from backend.api.endpoints.feeds.router import _temporary_stream_redirect

    response = _temporary_stream_redirect(
        "https://stream.example/master.m3u8?token=fresh",
        head_only=True,
        extra_headers={
            "Content-Type": "application/x-mpegURL",
            "Content-Disposition": 'inline; filename="video.m3u8"',
        },
    )
    assert response.status_code == 302
    assert response.headers["content-type"] == "application/x-mpegURL"
    assert response.headers["content-disposition"] == 'inline; filename="video.m3u8"'


def test_synthetic_hls_head_is_immediate_200_without_length():
    from backend.api.endpoints.feeds.hls_probe_experiments import (
        synthetic_hls_head_response,
    )

    response = synthetic_hls_head_response(filename="video-head200.m3u8")
    assert response.status_code == 200
    assert response.body == b""
    assert response.headers["content-type"] == "application/x-mpegURL"
    assert response.headers["content-disposition"] == (
        'inline; filename="video-head200.m3u8"'
    )
    assert "content-length" not in response.headers


def test_transparent_proxy_does_not_rewrite_playlist(monkeypatch):
    import backend.api.endpoints.feeds.hls_experiments as experiments

    playlist = b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1000\nhttps://cdn.example/video.m3u8?token=abc\n"

    class FakeUpstream:
        status = 200
        headers = {
            "Content-Type": "application/vnd.apple.mpegurl",
            "Content-Length": str(len(playlist)),
            "Cache-Control": "no-cache",
        }

        def read(self, _size):
            return playlist

        def close(self):
            pass

    monkeypatch.setattr(experiments, "urlopen", lambda *_args, **_kwargs: FakeUpstream())

    response = experiments.transparent_hls_proxy_response(
        "https://dailywire.example/master.m3u8?token=fresh",
        head_only=False,
        forced_media_type="application/x-mpegURL",
    )

    assert response.body == playlist
    assert response.headers["content-type"] == "application/x-mpegURL"
    assert response.headers["content-length"] == str(len(playlist))


def test_prewarmed_manifest_cache_keeps_raw_and_absolute_variants(
        tmp_path: Path,
        monkeypatch,
):
    import backend.api.endpoints.feeds.hls_probe_experiments as probes

    source_url = "https://cdn.example/show/master.m3u8?token=abc"
    playlist = b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=1000\nchild/video.m3u8\n"

    class FakeUpstream:
        headers = {
            "Content-Type": "application/vnd.apple.mpegurl",
            "Cache-Control": "no-cache",
        }

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def read(self, _size):
            return playlist

        def geturl(self):
            return source_url

    monkeypatch.setattr(probes, "_prefetch_root", lambda: tmp_path)
    monkeypatch.setattr(probes, "urlopen", lambda *_args, **_kwargs: FakeUpstream())

    probes.prewarm_hls_manifests("token:episode-1", source_url)
    assert probes.get_prefetched_hls_url("token:episode-1") == source_url

    raw = probes.prefetched_hls_manifest_response(
        "token:episode-1",
        absolute_children=False,
        head_only=False,
    )
    assert raw.body == playlist
    assert raw.headers["content-type"] == "application/vnd.apple.mpegurl"

    absolute = probes.prefetched_hls_manifest_response(
        "token:episode-1",
        absolute_children=True,
        head_only=False,
        forced_media_type="application/x-mpegURL",
    )
    assert (
        b"https://cdn.example/show/child/video.m3u8?token=abc"
        in absolute.body
    )
    assert absolute.headers["content-type"] == "application/x-mpegURL"


def test_media_routes_expose_filename_extensions():
    from backend.api.endpoints.feeds.router import router

    expected_paths = {
        "/feeds/rss/{token}/episodes/{episode_slug}/audio.m4a",
        "/feeds/rss/{token}/episodes/{episode_slug}/video.m3u8",
        "/feeds/rss/{token}/episodes/{episode_slug}/video-https.m3u8",
        "/feeds/rss/{token}/episodes/{episode_slug}/video-cached-302.m3u8",
        "/feeds/rss/{token}/episodes/{episode_slug}/video-head200.m3u8",
        "/feeds/rss/{token}/episodes/{episode_slug}/video-302-headers.m3u8",
        "/feeds/rss/{token}/episodes/{episode_slug}/video-prewarmed-raw.m3u8",
        "/feeds/rss/{token}/episodes/{episode_slug}/video-prewarmed-absolute.m3u8",
        "/feeds/rss/{token}/episodes/{episode_slug}/video-307.m3u8",
        "/feeds/rss/{token}/episodes/{episode_slug}/video-308.m3u8",
        "/feeds/rss/{token}/episodes/{episode_slug}/video-proxy.m3u8",
        "/feeds/rss/{token}/episodes/{episode_slug}/master.m3u8",
        "/feeds/rss/{token}/episodes/{episode_slug}/index.m3u8",
        "/feeds/rss/{token}/episodes/{episode_slug}/video-proxy-apple.m3u8",
        "/feeds/rss/{token}/episodes/{episode_slug}/video-proxy-generic.m3u8",
        "/feeds/rss/{token}/episodes/{episode_slug}/prepared/{resource_name}",
        "/feeds/rss/{token}/episodes/{episode_slug}/video.mp4",
        "/feeds/rss/{token}/episodes/{episode_slug}/download.{extension}",
    }
    routes = {route.path: route for route in router.routes if route.path in expected_paths}

    assert set(routes) == expected_paths
    for route in routes.values():
        assert {"GET", "HEAD"}.issubset(route.methods)
