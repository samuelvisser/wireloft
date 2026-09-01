from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit
from xml.etree.ElementTree import Element, tostring

import pytest


def _episode() -> SimpleNamespace:
    return SimpleNamespace(
        uuid="episode-uuid",
        slug="episode-slug",
        title="Episode title",
        description="Description",
        published_date=datetime(2026, 9, 1),
        went_live_date=None,
        created_at=datetime(2026, 9, 1),
        duration=1800.0,
        thumbnail_landscape_path=None,
        thumbnail_square_path=None,
        thumbnail_portrait_path=None,
    )


def test_direct_stream_uses_audio_enclosure_and_signed_hls_alternate():
    from backend.api.endpoints.feeds.service import _append_item

    channel = Element("channel")
    _append_item(
        channel,
        media_base_url="https://wireloft.test/feeds/rss/token",
        episode=_episode(),
        download=None,
        preferred_format="format_1080p",
        dw_video_method="stream_hls_download_m4a",
        dw_video_url="https://stream.dailywire.test/master.m3u8?token=fresh",
    )

    xml = tostring(channel, encoding="unicode")
    assert (
        '<enclosure url="https://wireloft.test/feeds/rss/token/episodes/episode-slug/audio" '
        'length="0" type="audio/mpeg"'
    ) in xml
    assert 'type="application/x-mpegURL"' in xml
    assert 'uri="https://stream.dailywire.test/master.m3u8?token=fresh"' in xml.replace("&amp;", "&")
    assert "episode-uuid:stream_hls_download_m4a" in xml


def test_cached_mp4_uses_video_enclosure_without_audio_fallback(monkeypatch):
    import backend.api.endpoints.feeds.service as service

    monkeypatch.setattr(service, "get_cached_mp4_size", lambda _uuid: 123456)
    channel = Element("channel")
    service._append_item(
        channel,
        media_base_url="https://wireloft.test/feeds/rss/token",
        episode=_episode(),
        download=None,
        preferred_format="format_1080p",
        dw_video_method="stream_download_mp4",
    )

    xml = tostring(channel, encoding="unicode")
    assert (
        '<enclosure url="https://wireloft.test/feeds/rss/token/episodes/episode-slug/video.mp4" '
        'length="123456" type="video/mp4"'
    ) in xml
    assert "/audio" not in xml
    assert "podcast:alternateEnclosure" not in xml
    assert "episode-uuid:stream_download_mp4" in xml


def test_downloaded_video_keeps_the_standard_download_enclosure(tmp_path):
    from backend.api.endpoints.feeds.service import _append_item

    file_path = tmp_path / "episode.mp4"
    file_path.write_bytes(b"video")
    download = SimpleNamespace(
        file_path=str(file_path),
        downloaded_bytes=0,
        local_media_profile=SimpleNamespace(preferred_format="format_1080p"),
    )
    channel = Element("channel")

    _append_item(
        channel,
        media_base_url="https://wireloft.test/feeds/rss/token",
        episode=_episode(),
        download=download,
        preferred_format="format_1080p",
        dw_video_method="stream_download_mp4",
    )

    xml = tostring(channel, encoding="unicode")
    assert (
        '<enclosure url="https://wireloft.test/feeds/rss/token/episodes/episode-slug" '
        'length="5" type="video/mp4"'
    ) in xml
    assert "/video.mp4" not in xml
    assert "podcast:alternateEnclosure" not in xml
    assert "episode-uuid:stream_download_mp4" not in xml


def test_feed_url_method_is_replaced_without_losing_other_query_parameters():
    from backend.utils.feed_urls import set_rss_feed_dw_video_method

    updated = set_rss_feed_dw_video_method(
        "https://wireloft.test/feed.xml?custom=value&dwVideoMethod=stream_hls_download_m4a",
        use_dw_stream=True,
        dw_video_method="stream_download_mp4",
    )

    query = parse_qs(urlsplit(updated).query)
    assert query == {
        "custom": ["value"],
        "dwVideoMethod": ["stream_download_mp4"],
    }


def test_feed_url_method_is_removed_when_dailywire_streaming_is_disabled():
    from backend.utils.feed_urls import set_rss_feed_dw_video_method

    updated = set_rss_feed_dw_video_method(
        "https://wireloft.test/feed.xml?dwVideoMethod=stream_download_mp4&custom=value",
        use_dw_stream=False,
        dw_video_method="stream_download_mp4",
    )

    assert parse_qs(urlsplit(updated).query) == {"custom": ["value"]}


def test_cached_mp4_is_prepared_once_and_reused(monkeypatch, tmp_path):
    import backend.api.endpoints.feeds.cached_video as cached_video

    target = tmp_path / "episode.mp4"
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        Path(command[-1]).write_bytes(b"prepared-video")
        return SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(cached_video, "_cache_path", lambda _uuid: target)
    monkeypatch.setattr(
        cached_video,
        "get_settings",
        lambda: SimpleNamespace(
            download_settings=SimpleNamespace(ffmpeg_path="ffmpeg")
        ),
    )
    monkeypatch.setattr(cached_video.subprocess, "run", fake_run)
    cached_video._CACHE_LOCKS.clear()

    first = cached_video.prepare_cached_mp4(
        "https://stream.dailywire.test/master.m3u8",
        episode_uuid="episode-uuid",
    )
    second = cached_video.prepare_cached_mp4(
        "https://stream.dailywire.test/master.m3u8",
        episode_uuid="episode-uuid",
    )

    assert first == target
    assert second == target
    assert target.read_bytes() == b"prepared-video"
    assert len(calls) == 1


def test_rss_head_response_has_matching_length_and_no_body():
    from backend.api.endpoints.feeds.router import _rss_response

    xml = b"<?xml version='1.0'?><rss />"
    response = _rss_response(xml, head_only=True)

    assert response.status_code == 200
    assert response.body == b""
    assert response.headers["content-length"] == str(len(xml))
    assert response.headers["content-type"] == "application/rss+xml; charset=utf-8"
    assert response.headers["cache-control"] == "no-store, no-cache, must-revalidate"


def test_uncached_mp4_head_does_not_claim_an_empty_file():
    from backend.api.endpoints.feeds.router import _cached_mp4_head_response

    response = _cached_mp4_head_response(None, filename="episode.mp4")

    assert response.status_code == 200
    assert response.body == b""
    assert response.headers["content-type"] == "video/mp4"
    assert response.headers["accept-ranges"] == "bytes"
    assert "content-length" not in response.headers


def test_feed_and_media_routes_accept_head_requests():
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
