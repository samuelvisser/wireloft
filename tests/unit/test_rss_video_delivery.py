from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
from types import SimpleNamespace
from xml.etree.ElementTree import Element

import pytest


def _episode():
    return SimpleNamespace(
        uuid="episode-uuid",
        slug="episode-1",
        title="Episode 1",
        description="Description",
        published_date=datetime(2026, 9, 1, tzinfo=timezone.utc),
        went_live_date=None,
        created_at=datetime(2026, 9, 1, tzinfo=timezone.utc),
        duration=1800.0,
        thumbnail_landscape_path=None,
        thumbnail_square_path=None,
        thumbnail_portrait_path=None,
    )


def _profile(mode: str):
    return SimpleNamespace(
        preferred_format="format_1080p",
        video_output_mode=mode,
    )


def _children(parent: Element, tag: str) -> list[Element]:
    return [child for child in parent if child.tag == tag]


@pytest.mark.parametrize(
    ("mode", "primary_type", "primary_suffix", "alternate_type", "alternate_suffix"),
    [
        ("audio_hls", "audio/mp4", "/audio.m4a", "application/x-mpegURL", "/video.m3u8"),
        ("audio_mp4", "audio/mp4", "/audio.m4a", "video/mp4", "/video.mp4"),
        ("mp4", "video/mp4", "/video.mp4", None, None),
        ("mp4_hls", "video/mp4", "/video.mp4", "application/x-mpegURL", "/video.m3u8"),
    ],
)
def test_rss_video_output_modes_use_stable_wireloft_urls(
        mode,
        primary_type,
        primary_suffix,
        alternate_type,
        alternate_suffix,
):
    from backend.api.endpoints.feeds.service import _append_item

    channel = Element("channel")
    _append_item(
        channel,
        media_base_url="https://wireloft.example/feeds/rss/token",
        episode=_episode(),
        profile=_profile(mode),
    )

    item = channel.find("item")
    assert item is not None
    enclosure = item.find("enclosure")
    assert enclosure is not None
    assert enclosure.attrib["type"] == primary_type
    assert enclosure.attrib["url"].endswith(primary_suffix)
    assert enclosure.attrib["length"] == "0"

    alternates = _children(item, "podcast:alternateEnclosure")
    if alternate_type is None:
        assert alternates == []
    else:
        assert len(alternates) == 1
        assert alternates[0].attrib["type"] == alternate_type
        source = _children(alternates[0], "podcast:source")[0]
        assert source.attrib["uri"].endswith(alternate_suffix)

    assert item.find("guid").text == "episode-uuid"


def test_audio_only_uses_stable_m4a_without_video_alternate():
    from backend.api.endpoints.feeds.service import _append_item

    profile = SimpleNamespace(
        preferred_format="format_audio_only",
        video_output_mode="audio_hls",
    )
    channel = Element("channel")
    _append_item(
        channel,
        media_base_url="https://wireloft.example/feeds/rss/token",
        episode=_episode(),
        profile=profile,
    )

    enclosure = channel.find("item/enclosure")
    assert enclosure is not None
    assert enclosure.attrib == {
        "url": "https://wireloft.example/feeds/rss/token/episodes/episode-1/audio.m4a",
        "length": "0",
        "type": "audio/mp4",
    }
    assert not _children(channel.find("item"), "podcast:alternateEnclosure")


def test_feed_url_does_not_encode_video_delivery_mode():
    from backend.utils.feed_urls import build_rss_feed_url

    request = SimpleNamespace(base_url="https://wireloft.example/")
    assert build_rss_feed_url(
        request,
        token="token",
        show_slug="show",
    ) == "https://wireloft.example/feeds/rss/token/show.xml"


def test_cached_mp4_path_uses_configured_rss_cache_root(monkeypatch, tmp_path):
    import backend.api.endpoints.feeds.cached_video as cached_video

    monkeypatch.setattr(
        cached_video,
        "get_settings",
        lambda: SimpleNamespace(
            download_settings=SimpleNamespace(rss_cache_root=tmp_path)
        ),
    )

    path = cached_video._cache_path("episode-uuid")

    assert path.parent == tmp_path / "video"
    assert path.suffix == ".mp4"


def test_rss_cache_cleanup_uses_configured_sliding_retention(monkeypatch, tmp_path):
    import backend.api.endpoints.feeds.cached_video as cached_video

    video_root = tmp_path / "video"
    video_root.mkdir()
    expired = video_root / "expired.mp4"
    current = video_root / "current.mp4"
    expired.write_bytes(b"expired")
    current.write_bytes(b"current")
    os.utime(expired, (900, 900))
    os.utime(current, (950, 950))

    settings = SimpleNamespace(
        download_settings=SimpleNamespace(
            rss_cache_root=tmp_path,
            rss_cache_retention_seconds=60,
        )
    )
    monkeypatch.setattr(cached_video, "get_settings", lambda: settings)
    monkeypatch.setattr(cached_video.time, "time", lambda: 1000)

    assert cached_video._is_current(current)
    assert not cached_video._is_current(expired)
    assert cached_video.cleanup_expired_rss_cache() == 1
    assert current.exists()
    assert not expired.exists()


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
            download_settings=SimpleNamespace(
                ffmpeg_path="ffmpeg",
                rss_cache_retention_seconds=7 * 24 * 60 * 60,
            )
        ),
    )
    monkeypatch.setattr(cached_video.subprocess, "run", fake_run)
    cached_video._CACHE_LOCKS.clear()

    first = cached_video.prepare_cached_mp4(
        "https://stream.dailywire.test/master.m3u8",
        episode_uuid="episode-uuid",
    )
    second = cached_video.prepare_cached_mp4(
        "https://stream.dailywire.test/new-master.m3u8",
        episode_uuid="episode-uuid",
    )

    assert first == target
    assert second == target
    assert target.read_bytes() == b"prepared-video"
    assert len(calls) == 1
    assert "+faststart" in calls[0]


def test_rss_head_response_has_matching_length_and_no_body():
    from backend.api.endpoints.feeds.router import _rss_response

    xml = b"<?xml version='1.0'?><rss />"
    response = _rss_response(xml, head_only=True)

    assert response.status_code == 200
    assert response.body == b""
    assert response.headers["content-length"] == str(len(xml))
    assert response.headers["content-type"] == "application/rss+xml; charset=utf-8"
    assert response.headers["cache-control"] == "no-store, no-cache, must-revalidate"


def test_uncached_mp4_head_does_not_start_or_claim_download():
    from backend.api.endpoints.feeds.router import _cached_mp4_head_response

    response = _cached_mp4_head_response(None, filename="episode.mp4")

    assert response.status_code == 200
    assert response.body == b""
    assert response.headers["content-type"] == "video/mp4"
    assert response.headers["accept-ranges"] == "bytes"
    assert "content-length" not in response.headers


def test_feed_and_stable_media_routes_accept_head_requests():
    from backend.api.endpoints.feeds.router import router

    expected_paths = {
        "/feeds/rss/{token}/{show_slug}.xml",
        "/feeds/rss/{token}/episodes/{episode_slug}",
        "/feeds/rss/{token}/episodes/{episode_slug}/audio.m4a",
        "/feeds/rss/{token}/episodes/{episode_slug}/video.mp4",
        "/feeds/rss/{token}/episodes/{episode_slug}/video.m3u8",
        "/feeds/rss/{token}/episodes/{episode_slug}/hls/{asset_path:path}",
    }
    routes = {route.path: route for route in router.routes if route.path in expected_paths}

    assert set(routes) == expected_paths
    for route in routes.values():
        assert {"GET", "HEAD"}.issubset(route.methods)
