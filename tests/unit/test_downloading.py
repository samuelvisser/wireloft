from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


# ---------- dailywire_downloader: HLS parsing ----------

MASTER = """#EXTM3U
#EXT-X-VERSION:5
#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="sub1",NAME="English",URI="https://cdn.example/subs.m3u8"
#EXT-X-STREAM-INF:BANDWIDTH=2183500,AVERAGE-BANDWIDTH=2183500,CODECS="mp4a.40.2,avc1.640020",RESOLUTION=1280x720
https://cdn.example/720/rendition.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=4273500,CODECS="mp4a.40.2,avc1.64002a",RESOLUTION=1920x1080
1080/rendition.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=569800,RESOLUTION=480x270
https://cdn.example/270/rendition.m3u8
"""

MEDIA = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:6
#EXT-X-PLAYLIST-TYPE:VOD
#EXTINF:5,
https://cdn.example/chunk/0.ts
#EXTINF:5,
chunk/1.ts
#EXTINF:3.2,
https://cdn.example/chunk/2.ts
#EXT-X-ENDLIST
"""


def test_parse_master_playlist_extracts_renditions():
    from dailywire_downloader.hls import parse_master_playlist

    renditions = parse_master_playlist(MASTER, base_url="https://cdn.example/master.m3u8")
    assert [(r.width, r.height, r.bandwidth) for r in renditions] == [
        (1280, 720, 2183500),
        (1920, 1080, 4273500),
        (480, 270, 569800),
    ]
    # Relative URI resolves against the master URL
    assert renditions[1].url == "https://cdn.example/1080/rendition.m3u8"
    assert renditions[0].codecs == "mp4a.40.2,avc1.640020"


def test_parse_media_playlist_extracts_segments():
    from dailywire_downloader.hls import parse_media_playlist

    playlist = parse_media_playlist(MEDIA, base_url="https://cdn.example/480/rendition.m3u8")
    assert playlist.is_endlist
    assert playlist.init_segment_url is None
    assert playlist.segment_urls == (
        "https://cdn.example/chunk/0.ts",
        "https://cdn.example/480/chunk/1.ts",
        "https://cdn.example/chunk/2.ts",
    )


def test_parse_media_playlist_rejects_encryption():
    from dailywire_downloader.errors import EncryptedMediaError
    from dailywire_downloader.hls import parse_media_playlist

    encrypted = MEDIA.replace(
        "#EXT-X-TARGETDURATION:6",
        '#EXT-X-TARGETDURATION:6\n#EXT-X-KEY:METHOD=AES-128,URI="https://cdn.example/key"',
    )
    with pytest.raises(EncryptedMediaError):
        parse_media_playlist(encrypted, base_url="https://cdn.example/x.m3u8")


def test_probe_kinds_via_suggested_extension():
    from dailywire_downloader.models import MediaInfo, MediaKind

    hls = MediaInfo(url="https://x/master.m3u8", kind=MediaKind.HLS_MASTER)
    assert hls.suggested_extension == "ts"

    audio = MediaInfo(url="https://x/audio.m4a?token=1", kind=MediaKind.DIRECT_FILE, content_type="audio/m4a")
    assert audio.suggested_extension == "m4a"

    unknown = MediaInfo(url="https://x/file", kind=MediaKind.DIRECT_FILE)
    assert unknown.suggested_extension == "bin"


# ---------- resolution selection (application logic) ----------

def _rendition(height: int, bandwidth: int = 1000):
    from dailywire_downloader import VideoRendition

    return VideoRendition(url=f"https://x/{height}.m3u8", width=height * 16 // 9,
                          height=height, bandwidth=bandwidth, codecs=None)


def test_select_rendition_prefers_smallest_at_or_above_request():
    from task_manager.tasks.workers.download_episode._helpers import select_rendition

    renditions = [_rendition(270), _rendition(480), _rendition(720), _rendition(1080)]
    assert select_rendition(renditions, 720).height == 720
    assert select_rendition(renditions, 600).height == 720
    assert select_rendition(renditions, 1080).height == 1080


def test_select_rendition_falls_back_to_highest_available():
    from task_manager.tasks.workers.download_episode._helpers import select_rendition

    renditions = [_rendition(270), _rendition(480), _rendition(720), _rendition(1080)]
    # 4K requested but nothing at or above it: take the highest that exists
    assert select_rendition(renditions, 2160).height == 1080


def test_select_rendition_requires_resolutions():
    from dailywire_downloader import MediaUnavailableError, VideoRendition
    from task_manager.tasks.workers.download_episode._helpers import select_rendition

    nameless = VideoRendition(url="https://x/a.m3u8", width=None, height=None, bandwidth=None, codecs=None)
    with pytest.raises(MediaUnavailableError):
        select_rendition([nameless], 1080)


# ---------- output template resolution ----------

def _db_with_episode():
    from backend.db import Base
    from backend.db.models import Episode, Season, Show
    from backend.types.show_types import EpisodeIdentifier, ShowType
    from backend.utils.helpers import generate_uuid

    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    show = Show(
        uuid="show-uuid",
        slug="test-show",
        title="Test Show",
        description=None,
        sharing_url="https://example.test/show",
        membership_level="FREE",
        type=ShowType.PODCAST.value,
        episode_identifier=EpisodeIdentifier.NUMBERED.value,
        author_name="Host",
        author_slug="host",
    )
    season = Season(show=show, index=1, slug="season-2026", name="2026")
    episode = Episode(
        uuid=generate_uuid(),
        type="episode",
        show=show,
        season=season,
        index=1,
        episode_identifier="ep.101",
        slug="test-episode-101",
        title="Ep. 101: A/B <Testing>",
        description=None,
        duration=100.0,
        publish_status="published_final",
        sharing_url="https://example.test/ep",
    )
    session.add_all([show, season, episode])
    session.commit()
    return session, engine, episode


def test_resolve_episode_output_path(tmp_path, monkeypatch):
    from config import get_settings
    from backend.utils.output_template import resolve_episode_output_path

    session, engine, episode = _db_with_episode()
    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)

    path = resolve_episode_output_path(
        "/downloads/audio/{show}/{season}/{ep_id} - {episode}.ext",
        episode=episode,
        extension="m4a",
    )
    assert path == tmp_path.resolve() / "audio" / "test-show" / "season-2026" / "ep.101 - test-episode-101.m4a"

    # Unsafe characters in substitutions never escape into the path structure
    titled = resolve_episode_output_path("/downloads/{title}.ext", episode=episode, extension="ts")
    assert titled.parent == tmp_path.resolve()
    assert "/" not in titled.name and "<" not in titled.name

    # Without a known extension the template's .ext marker is kept
    pending = resolve_episode_output_path("/downloads/{show}/{episode}.ext", episode=episode)
    assert pending.name == "test-episode-101.ext"

    session.close()
    engine.dispose()


# ---------- one download per profile ----------

def test_create_episode_download_enforces_one_per_profile(monkeypatch, tmp_path):
    from fastapi import HTTPException

    from backend.api.endpoints.media_downloads.service import create_episode_download
    from backend.api.models.media_download import EpisodeDownloadAPICreate
    from backend.db.models import LocalMediaProfile
    from backend.types.download_profile_types import MediaDownloadStatus
    from config import get_settings

    session, engine, episode = _db_with_episode()
    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)

    profile = LocalMediaProfile(
        slug="audio",
        name="Audio",
        output_template="/downloads/{show}/{episode}.ext",
        preferred_format="format_audio_only",
    )
    session.add(profile)
    session.commit()

    body = EpisodeDownloadAPICreate(local_media_profile_id=profile.id)
    download = create_episode_download(session, episode.slug, body)
    session.commit()
    assert download.download_status == MediaDownloadStatus.PENDING.value
    assert download.file_path.endswith("test-episode-101.ext")

    # Second request for the same profile: pending row is reused, not duplicated
    again = create_episode_download(session, episode.slug, body)
    session.commit()
    assert again.id == download.id

    # An active download is a conflict
    download.download_status = MediaDownloadStatus.DOWNLOADING.value
    session.commit()
    with pytest.raises(HTTPException) as exc_info:
        create_episode_download(session, episode.slug, body)
    assert exc_info.value.status_code == 409

    # A finished download is a conflict too (one download per profile)
    download.download_status = MediaDownloadStatus.DOWNLOADED.value
    session.commit()
    with pytest.raises(HTTPException):
        create_episode_download(session, episode.slug, body)

    # An errored download is restarted in place
    download.download_status = MediaDownloadStatus.ERROR.value
    download.error_message = "boom"
    session.commit()
    restarted = create_episode_download(session, episode.slug, body)
    session.commit()
    assert restarted.id == download.id
    assert restarted.download_status == MediaDownloadStatus.PENDING.value
    assert restarted.error_message is None

    session.close()
    engine.dispose()
