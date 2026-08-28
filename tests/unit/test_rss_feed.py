from __future__ import annotations

import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


class _FakeURL:
    def __init__(self, value: str):
        self._value = value

    def __str__(self) -> str:
        return self._value


class _FakeRequest:
    def __init__(self, base_url: str = "http://localhost:5001/"):
        self.base_url = _FakeURL(base_url)


def _make_show(session, *, slug="test-show"):
    from backend.db.models import Show
    from backend.types.show_types import EpisodeIdentifier, ShowType

    show = Show(
        uuid=f"{slug}-uuid",
        slug=slug,
        title="Test Show",
        description="A great show",
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


def _make_season(session, show, *, index=1, slug="season-1", name="One"):
    from backend.db.models import Season

    season = Season(show=show, index=index, slug=slug, name=name)
    session.add(season)
    session.flush()
    return season


def _make_episode(session, show, season, *, slug, index, published_at=None):
    from backend.db.models import Episode
    from backend.utils.helpers import generate_uuid

    episode = Episode(
        uuid=generate_uuid(),
        type="episode",
        show=show,
        season=season,
        index=index,
        episode_identifier=f"ep.{index}",
        slug=slug,
        title=f"Episode {index}",
        description=f"Description {index}",
        duration=1800.0,
        publish_status="published_final",
        sharing_url=f"https://example.test/{slug}",
        published_date=published_at,
    )
    session.add(episode)
    session.flush()
    return episode


def _make_local_media_profile(session, *, slug, preferred_format):
    from backend.db.models import LocalMediaProfile

    profile = LocalMediaProfile(
        slug=slug, name=slug,
        output_template="/downloads/{show}/{episode}.ext",
        preferred_format=preferred_format,
    )
    session.add(profile)
    session.flush()
    return profile


def _make_download(session, episode, profile, *, status, file_path=None, finished_at=None):
    from backend.db.models.media_download import EpisodeMediaDownload
    from backend.types.media_types import MediaType

    download = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=episode.id,
        local_media_profile_id=profile.id,
        download_status=status,
        file_path=file_path or f"/downloads/{episode.slug}.ext",
        progress=100,
        finished_at=finished_at,
    )
    session.add(download)
    session.flush()
    return download


def _make_rss_profile(session, show, *, preferred_format="format_1080p", require_exact_match=False,
                       use_downloads=True, use_dw_stream=False, enable_profile=True, token="tok"):
    from backend.db.models.stream_profile import RssStreamProfile

    profile = RssStreamProfile(
        show=show, enable_profile=enable_profile, use_downloads=use_downloads, use_dw_stream=use_dw_stream,
        preferred_format=preferred_format, require_exact_match=require_exact_match,
        token=token, feed_url=f"http://localhost:5001/feeds/rss/{token}/{show.slug}.xml",
    )
    session.add(profile)
    session.flush()
    return profile


@pytest.fixture
def db_session(tmp_path):
    import backend.db.models  # noqa: F401 (registers all mappers before create_all)
    from backend.db import Base

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    yield session
    session.close()
    engine.dispose()


@pytest.fixture
def real_file(tmp_path):
    def _make(name: str, size: int = 2048) -> str:
        path = tmp_path / name
        path.write_bytes(b"x" * size)
        return str(path)

    return _make


# ---------- _select_best_download ----------

def test_select_best_download_prefers_exact_match(db_session, real_file):
    from backend.api.endpoints.feeds.service import _select_best_download

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    ep = _make_episode(db_session, show, season, slug="ep-1", index=1)
    lmp_720 = _make_local_media_profile(db_session, slug="v720", preferred_format="format_720p")
    lmp_1080 = _make_local_media_profile(db_session, slug="v1080", preferred_format="format_1080p")

    d720 = _make_download(db_session, ep, lmp_720, status="downloaded", file_path=real_file("a.mp4"))
    d1080 = _make_download(db_session, ep, lmp_1080, status="downloaded", file_path=real_file("b.mp4"))

    best = _select_best_download([d720, d1080], preferred_format="format_1080p", require_exact_match=False)
    assert best.id == d1080.id


def test_select_best_download_falls_back_when_not_exact(db_session, real_file):
    from backend.api.endpoints.feeds.service import _select_best_download

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    ep = _make_episode(db_session, show, season, slug="ep-1", index=1)
    lmp_720 = _make_local_media_profile(db_session, slug="v720", preferred_format="format_720p")

    d720 = _make_download(db_session, ep, lmp_720, status="downloaded", file_path=real_file("a.mp4"))

    # Wanted 1080p, only 720p downloaded: falls back when exact match isn't required.
    best = _select_best_download([d720], preferred_format="format_1080p", require_exact_match=False)
    assert best.id == d720.id

    # ... but not when an exact match is required.
    best_strict = _select_best_download([d720], preferred_format="format_1080p", require_exact_match=True)
    assert best_strict is None


def test_select_best_download_never_mixes_audio_and_video(db_session, real_file):
    from backend.api.endpoints.feeds.service import _select_best_download

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    ep = _make_episode(db_session, show, season, slug="ep-1", index=1)
    lmp_audio = _make_local_media_profile(db_session, slug="audio", preferred_format="format_audio_only")

    d_audio = _make_download(db_session, ep, lmp_audio, status="downloaded", file_path=real_file("a.m4a"))

    # Preferred format is video: an audio-only download is never substituted, exact match or not.
    assert _select_best_download([d_audio], preferred_format="format_1080p", require_exact_match=False) is None
    assert _select_best_download([d_audio], preferred_format="format_1080p", require_exact_match=True) is None


def test_select_best_download_ignores_unavailable_statuses(db_session, real_file):
    from backend.api.endpoints.feeds.service import get_feed_items

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    ep = _make_episode(db_session, show, season, slug="ep-1", index=1, published_at=datetime.now(timezone.utc).replace(tzinfo=None))
    lmp = _make_local_media_profile(db_session, slug="audio", preferred_format="format_audio_only")

    _make_download(db_session, ep, lmp, status="missing", file_path=real_file("a.m4a"))
    profile = _make_rss_profile(db_session, show, preferred_format="format_audio_only")

    assert get_feed_items(db_session, profile) == []


# ---------- get_feed_items ----------

def test_get_feed_items_orders_newest_first_and_scopes_by_show(db_session, real_file):
    from backend.api.endpoints.feeds.service import get_feed_items

    show = _make_show(db_session, slug="show-a")
    other_show = _make_show(db_session, slug="show-b")
    season = _make_season(db_session, show, slug="show-a-season-1")
    other_season = _make_season(db_session, other_show, slug="show-b-season-1")
    lmp = _make_local_media_profile(db_session, slug="audio", preferred_format="format_audio_only")

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    older = _make_episode(db_session, show, season, slug="older", index=1, published_at=now - timedelta(days=5))
    newer = _make_episode(db_session, show, season, slug="newer", index=2, published_at=now)
    other = _make_episode(db_session, other_show, other_season, slug="other", index=1, published_at=now)

    _make_download(db_session, older, lmp, status="downloaded", file_path=real_file("older.m4a"))
    _make_download(db_session, newer, lmp, status="redownloaded", file_path=real_file("newer.m4a"))
    _make_download(db_session, other, lmp, status="downloaded", file_path=real_file("other.m4a"))

    profile = _make_rss_profile(db_session, show, preferred_format="format_audio_only")
    items = get_feed_items(db_session, profile)

    assert [ep.slug for ep, _ in items] == ["newer", "older"]


def test_get_feed_items_empty_when_use_downloads_disabled(db_session, real_file):
    from backend.api.endpoints.feeds.service import get_feed_items

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    ep = _make_episode(db_session, show, season, slug="ep-1", index=1)
    lmp = _make_local_media_profile(db_session, slug="audio", preferred_format="format_audio_only")
    _make_download(db_session, ep, lmp, status="downloaded", file_path=real_file("a.m4a"))

    profile = _make_rss_profile(db_session, show, preferred_format="format_audio_only", use_downloads=False)
    assert get_feed_items(db_session, profile) == []


# ---------- get_download_for_episode / get_rss_stream_profile_by_token ----------

def test_get_rss_stream_profile_by_token_404s_for_unknown_or_disabled(db_session):
    from fastapi import HTTPException
    from backend.api.endpoints.feeds.service import get_rss_stream_profile_by_token

    show = _make_show(db_session)
    _make_rss_profile(db_session, show, token="known", enable_profile=False)

    with pytest.raises(HTTPException) as exc:
        get_rss_stream_profile_by_token(db_session, "unknown-token")
    assert exc.value.status_code == 404

    with pytest.raises(HTTPException):
        get_rss_stream_profile_by_token(db_session, "known")


def test_get_download_for_episode_404s_when_nothing_matches(db_session, real_file):
    from fastapi import HTTPException
    from backend.api.endpoints.feeds.service import get_download_for_episode

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    ep = _make_episode(db_session, show, season, slug="ep-1", index=1)
    profile = _make_rss_profile(db_session, show, preferred_format="format_audio_only")

    with pytest.raises(HTTPException) as exc:
        get_download_for_episode(db_session, profile, "does-not-exist")
    assert exc.value.status_code == 404

    with pytest.raises(HTTPException) as exc2:
        get_download_for_episode(db_session, profile, ep.slug)
    assert exc2.value.status_code == 404


# ---------- render_rss_feed ----------

def test_render_rss_feed_includes_enclosure_and_metadata(db_session, real_file):
    from backend.api.endpoints.feeds.service import render_rss_feed

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    ep = _make_episode(db_session, show, season, slug="ep-1", index=1, published_at=datetime.now(timezone.utc).replace(tzinfo=None))
    lmp = _make_local_media_profile(db_session, slug="audio", preferred_format="format_audio_only")
    _make_download(db_session, ep, lmp, status="downloaded", file_path=real_file("ep-1.mp3", size=4096))

    profile = _make_rss_profile(db_session, show, preferred_format="format_audio_only", token="tok-123")

    xml = render_rss_feed(db_session, _FakeRequest(), profile).decode("utf-8")

    assert "<title>Test Show</title>" in xml
    assert "<title>Episode 1</title>" in xml
    assert "http://localhost:5001/feeds/rss/tok-123/episodes/ep-1" in xml
    assert 'length="4096"' in xml
    assert "audio/mpeg" in xml


def test_render_rss_feed_handles_missing_file_gracefully(db_session, tmp_path):
    """A download row can outlive its file between file-watcher runs; the
    enclosure should still be produced (length falls back to downloaded_bytes)
    rather than crashing the feed."""
    from backend.api.endpoints.feeds.service import render_rss_feed

    show = _make_show(db_session)
    season = _make_season(db_session, show)
    ep = _make_episode(db_session, show, season, slug="ep-1", index=1)
    lmp = _make_local_media_profile(db_session, slug="audio", preferred_format="format_audio_only")
    _make_download(db_session, ep, lmp, status="downloaded", file_path=str(tmp_path / "does-not-exist.mp3"))

    profile = _make_rss_profile(db_session, show, preferred_format="format_audio_only")
    xml = render_rss_feed(db_session, _FakeRequest(), profile).decode("utf-8")
    assert "<enclosure" in xml
    assert 'length="0"' in xml


# ---------- create / regenerate (rss_stream_profiles service) ----------

def test_create_stream_profile_rss_autogenerates_feed_url(db_session):
    from backend.api.endpoints.rss_stream_profiles.service import create_stream_profile_rss
    from backend.api.models.rss_stream_profile import RssStreamProfileAPICreate

    show = _make_show(db_session)
    body = RssStreamProfileAPICreate(
        show_id=show.id, enable_profile=True, use_downloads=True, use_dw_stream=False,
        preferred_format="format_1080p", require_exact_match=False,
    )
    created = create_stream_profile_rss(db_session, _FakeRequest(), body)

    assert created.feed_url.startswith("http://localhost:5001/feeds/rss/")
    assert created.feed_url.endswith(f"/{show.slug}.xml")


def test_create_stream_profile_rss_respects_explicit_feed_url(db_session):
    from backend.api.endpoints.rss_stream_profiles.service import create_stream_profile_rss
    from backend.api.models.rss_stream_profile import RssStreamProfileAPICreate

    show = _make_show(db_session)
    body = RssStreamProfileAPICreate(
        show_id=show.id, enable_profile=True, use_downloads=True, use_dw_stream=False,
        preferred_format="format_1080p", require_exact_match=False,
        feed_url="https://my.custom.domain/feed.xml",
    )
    created = create_stream_profile_rss(db_session, _FakeRequest(), body)
    assert created.feed_url == "https://my.custom.domain/feed.xml"


def test_regenerate_token_rotates_url_and_invalidates_old_token(db_session):
    from backend.api.endpoints.rss_stream_profiles.service import (
        create_stream_profile_rss,
        regenerate_stream_profile_rss_token,
    )
    from backend.api.endpoints.feeds.service import get_rss_stream_profile_by_token
    from backend.api.models.rss_stream_profile import RssStreamProfileAPICreate
    from fastapi import HTTPException

    show = _make_show(db_session)
    body = RssStreamProfileAPICreate(
        show_id=show.id, enable_profile=True, use_downloads=True, use_dw_stream=False,
        preferred_format="format_1080p", require_exact_match=False,
    )
    created = create_stream_profile_rss(db_session, _FakeRequest(), body)
    old_url = created.feed_url

    regenerated = regenerate_stream_profile_rss_token(db_session, _FakeRequest(), created.id)

    assert regenerated.feed_url != old_url
    assert regenerated.feed_url.startswith("http://localhost:5001/feeds/rss/")

    # The old token no longer resolves to anything.
    old_token = old_url.split("/feeds/rss/")[1].split("/")[0]
    with pytest.raises(HTTPException):
        get_rss_stream_profile_by_token(db_session, old_token)
