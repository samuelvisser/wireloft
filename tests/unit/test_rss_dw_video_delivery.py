from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from xml.etree.ElementTree import Element

import pytest


PODCASTING_2_0 = "podcasting_2_0"
CACHED_MP4 = "cached_mp4"
HYBRID = "podcasting_2_0_cached_mp4"


def _episode(*, slug: str = "episode-1", uuid: str = "episode-uuid"):
    return SimpleNamespace(
        title="Episode 1",
        uuid=uuid,
        slug=slug,
        description="Ben & Jeremy",
        published_date=datetime(2026, 9, 1, tzinfo=timezone.utc),
        went_live_date=None,
        created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        duration=1800.0,
        thumbnail_landscape_path=None,
        thumbnail_square_path=None,
        thumbnail_portrait_path=None,
    )


def _children(parent: Element, tag: str) -> list[Element]:
    return [child for child in parent if child.tag == tag]


def test_podcasting_2_0_uses_direct_hls_with_audio_fallback():
    from backend.api.endpoints.feeds.service import _append_item

    channel = Element("channel")
    signed_url = "https://stream.example/video.m3u8?token=abc&expires=123"
    _append_item(
        channel,
        media_base_url="https://wireloft.example/feeds/rss/token",
        episode=_episode(),
        download=None,
        preferred_format="format_1080p",
        dw_video_method=PODCASTING_2_0,
        dw_video_url=signed_url,
    )

    item = channel.find("item")
    assert item is not None
    enclosure = item.find("enclosure")
    assert enclosure is not None
    assert enclosure.attrib == {
        "url": "https://wireloft.example/feeds/rss/token/episodes/episode-1/audio",
        "length": "0",
        "type": "audio/mpeg",
    }

    alternates = _children(item, "podcast:alternateEnclosure")
    assert len(alternates) == 1
    assert alternates[0].attrib["type"] == "application/x-mpegURL"
    assert alternates[0].attrib["height"] == "1080"
    sources = _children(alternates[0], "podcast:source")
    assert len(sources) == 1
    assert sources[0].attrib["uri"] == signed_url


def test_cached_mp4_uses_video_enclosure_without_audio(monkeypatch):
    import backend.api.endpoints.feeds.service as feed_service

    monkeypatch.setattr(feed_service, "get_cached_mp4_size", lambda _uuid: 123456)

    channel = Element("channel")
    feed_service._append_item(
        channel,
        media_base_url="https://wireloft.example/feeds/rss/token",
        episode=_episode(),
        download=None,
        preferred_format="format_1080p",
        dw_video_method=CACHED_MP4,
    )

    item = channel.find("item")
    assert item is not None
    enclosure = item.find("enclosure")
    assert enclosure is not None
    assert enclosure.attrib == {
        "url": "https://wireloft.example/feeds/rss/token/episodes/episode-1/video.mp4",
        "length": "123456",
        "type": "video/mp4",
    }
    assert not _children(item, "podcast:alternateEnclosure")


def test_hybrid_uses_direct_hls_with_cached_mp4_fallback(monkeypatch):
    import backend.api.endpoints.feeds.service as feed_service

    monkeypatch.setattr(feed_service, "get_cached_mp4_size", lambda _uuid: 123456)
    signed_url = "https://stream.example/video.m3u8?token=abc&expires=123"

    channel = Element("channel")
    feed_service._append_item(
        channel,
        media_base_url="https://wireloft.example/feeds/rss/token",
        episode=_episode(),
        download=None,
        preferred_format="format_1080p",
        dw_video_method=HYBRID,
        dw_video_url=signed_url,
    )

    item = channel.find("item")
    assert item is not None
    enclosure = item.find("enclosure")
    assert enclosure is not None
    assert enclosure.attrib == {
        "url": "https://wireloft.example/feeds/rss/token/episodes/episode-1/video.mp4",
        "length": "123456",
        "type": "video/mp4",
    }

    alternates = _children(item, "podcast:alternateEnclosure")
    assert len(alternates) == 1
    sources = _children(alternates[0], "podcast:source")
    assert len(sources) == 1
    assert sources[0].attrib["uri"] == signed_url


@pytest.mark.parametrize("method", [PODCASTING_2_0, CACHED_MP4, HYBRID])
def test_local_download_keeps_download_only_feed_behavior(tmp_path, monkeypatch, method):
    import backend.api.endpoints.feeds.service as feed_service

    file_path = tmp_path / "episode.mp4"
    file_path.write_bytes(b"video-data")
    download = SimpleNamespace(
        file_path=str(file_path),
        downloaded_bytes=0,
        local_media_profile=SimpleNamespace(preferred_format="format_1080p"),
    )
    monkeypatch.setattr(
        feed_service,
        "get_cached_mp4_size",
        lambda _uuid: pytest.fail("cache must not be consulted for local downloads"),
    )

    channel = Element("channel")
    feed_service._append_item(
        channel,
        media_base_url="https://wireloft.example/feeds/rss/token",
        episode=_episode(),
        download=download,
        preferred_format="format_1080p",
        dw_video_method=method,
    )

    item = channel.find("item")
    assert item is not None
    enclosure = item.find("enclosure")
    assert enclosure is not None
    assert enclosure.attrib == {
        "url": "https://wireloft.example/feeds/rss/token/episodes/episode-1",
        "length": str(file_path.stat().st_size),
        "type": "video/mp4",
    }
    assert item.find("guid").text == "episode-uuid"
    assert not _children(item, "podcast:alternateEnclosure")


def test_remote_video_guid_changes_with_delivery_method():
    from backend.api.endpoints.feeds.service import _append_item

    values = []
    for method in (PODCASTING_2_0, CACHED_MP4, HYBRID):
        channel = Element("channel")
        _append_item(
            channel,
            media_base_url="https://wireloft.example/feeds/rss/token",
            episode=_episode(),
            download=None,
            preferred_format="format_1080p",
            dw_video_method=method,
            dw_video_url="https://stream.example/video.m3u8",
        )
        values.append(channel.find("item/guid").text)

    assert values == [
        "episode-uuid:podcasting_2_0",
        "episode-uuid:cached_mp4",
        "episode-uuid:podcasting_2_0_cached_mp4",
    ]


def test_feed_url_method_is_added_replaced_and_removed():
    from backend.utils.feed_urls import set_rss_feed_video_method

    original = "https://wireloft.example/feed.xml?custom=value"
    direct = set_rss_feed_video_method(
        original,
        use_dw_stream=True,
        dw_video_method=PODCASTING_2_0,
    )
    cached = set_rss_feed_video_method(
        direct,
        use_dw_stream=True,
        dw_video_method=CACHED_MP4,
    )
    hybrid = set_rss_feed_video_method(
        cached,
        use_dw_stream=True,
        dw_video_method=HYBRID,
    )
    disabled = set_rss_feed_video_method(
        hybrid,
        use_dw_stream=False,
        dw_video_method=HYBRID,
    )

    assert direct == (
        "https://wireloft.example/feed.xml?custom=value&"
        "dwVideoMethod=podcasting_2_0"
    )
    assert cached == (
        "https://wireloft.example/feed.xml?custom=value&dwVideoMethod=cached_mp4"
    )
    assert hybrid == (
        "https://wireloft.example/feed.xml?custom=value&"
        "dwVideoMethod=podcasting_2_0_cached_mp4"
    )
    assert disabled == original


def test_build_feed_url_includes_selected_method():
    from backend.utils.feed_urls import build_rss_feed_url

    request = SimpleNamespace(base_url="https://wireloft.example/")
    assert build_rss_feed_url(
        request,
        token="token",
        show_slug="test-show",
        use_dw_stream=True,
        dw_video_method=HYBRID,
    ) == (
        "https://wireloft.example/feeds/rss/token/test-show.xml?"
        "dwVideoMethod=podcasting_2_0_cached_mp4"
    )


def test_cached_mp4_is_prepared_once_and_reused(tmp_path, monkeypatch):
    import backend.api.endpoints.feeds.cached_video as cached_video

    target = tmp_path / "cached.mp4"
    monkeypatch.setattr(cached_video, "_cache_path", lambda _uuid: target)
    commands: list[list[str]] = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        Path(command[-1]).write_bytes(b"prepared-mp4")
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(cached_video.subprocess, "run", fake_run)

    first = cached_video.prepare_cached_mp4(
        "https://stream.example/video.m3u8",
        episode_uuid="episode-uuid",
    )
    second = cached_video.prepare_cached_mp4(
        "https://stream.example/new-signed-url.m3u8",
        episode_uuid="episode-uuid",
    )

    assert first == target
    assert second == target
    assert target.read_bytes() == b"prepared-mp4"
    assert len(commands) == 1
    assert commands[0][commands[0].index("-c") + 1] == "copy"
    assert "+faststart" in commands[0]


def test_feed_and_media_head_responses_have_matching_headers():
    from backend.api.endpoints.feeds.router import (
        _cached_mp4_head_response,
        _rss_response,
        _temporary_stream_redirect,
    )

    xml = b"<?xml version='1.0'?><rss />"
    feed = _rss_response(xml, head_only=True)
    assert feed.status_code == 200
    assert feed.body == b""
    assert feed.headers["content-length"] == str(len(xml))
    assert feed.headers["cache-control"] == "no-store, no-cache, must-revalidate"

    redirect = _temporary_stream_redirect(
        "https://stream.example/audio.mp3?token=fresh",
        head_only=True,
    )
    assert redirect.status_code == 302
    assert redirect.body == b""
    assert redirect.headers["location"].startswith("https://stream.example/")
    assert redirect.headers["cache-control"] == "no-store, no-cache, must-revalidate"

    uncached = _cached_mp4_head_response(None, filename="episode.mp4")
    assert uncached.status_code == 200
    assert uncached.body == b""
    assert "content-length" not in uncached.headers
    assert uncached.headers["accept-ranges"] == "bytes"

    cached_file = SimpleNamespace(stat=lambda: SimpleNamespace(st_size=321))
    cached = _cached_mp4_head_response(cached_file, filename="episode.mp4")
    assert cached.headers["content-length"] == "321"


def test_feed_routes_support_get_and_head():
    from backend.api.endpoints.feeds.router import router

    expected_paths = {
        "/feeds/rss/{token}/{show_slug}.xml",
        "/feeds/rss/{token}/episodes/{episode_slug}",
        "/feeds/rss/{token}/episodes/{episode_slug}/audio",
        "/feeds/rss/{token}/episodes/{episode_slug}/video.mp4",
    }
    routes = {route.path: route for route in router.routes if route.path in expected_paths}

    assert set(routes) == expected_paths
    for route in routes.values():
        assert {"GET", "HEAD"}.issubset(route.methods)
