from __future__ import annotations

from conftest import mark_artifact_available
import asyncio
from unittest.mock import Mock

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
    from dailywire_downloader.source import select_rendition

    renditions = [_rendition(270), _rendition(480), _rendition(720), _rendition(1080)]
    assert select_rendition(renditions, 720).height == 720
    assert select_rendition(renditions, 600).height == 720
    assert select_rendition(renditions, 1080).height == 1080


def test_select_rendition_falls_back_to_highest_available():
    from dailywire_downloader.source import select_rendition

    renditions = [_rendition(270), _rendition(480), _rendition(720), _rendition(1080)]
    # 4K requested but nothing at or above it: take the highest that exists
    assert select_rendition(renditions, 2160).height == 1080


def test_select_rendition_requires_resolutions():
    from dailywire_downloader import MediaUnavailableError, VideoRendition
    from dailywire_downloader.source import select_rendition

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
        "/downloads/audio/{{ show }}/{{ season }}/{{ episode_identifier }} - {{ episode }}.ext",
        episode=episode,
        extension="m4a",
    )
    assert path == tmp_path.resolve() / "audio" / "test-show" / "season-2026" / "ep.101 - test-episode-101.m4a"

    # Unsafe characters in substitutions never escape into the path structure
    titled = resolve_episode_output_path("/downloads/{{ title }}.ext", episode=episode, extension="ts")
    assert titled.parent == tmp_path.resolve()
    assert "/" not in titled.name and "<" not in titled.name

    # Without a known extension the template's .ext marker is kept
    pending = resolve_episode_output_path("/downloads/{{ show }}/{{ episode }}.ext", episode=episode)
    assert pending.name == "test-episode-101.ext"

    session.close()
    engine.dispose()


# ---------- one download per profile ----------

def test_create_episode_download_enforces_one_per_profile(monkeypatch, tmp_path):
    from fastapi import HTTPException

    from backend.api.endpoints.media_downloads.service import create_episode_download
    from backend.api.models.media_download import EpisodeDownloadAPICreate
    from backend.db.models import ShowLocalMediaProfile
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from config import get_settings

    session, engine, episode = _db_with_episode()
    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)

    profile = ShowLocalMediaProfile(
        slug="audio",
        name="Audio",
        output_template="/downloads/{{ show }}/{{ episode }}.ext",
        preferred_format="format_audio_only",
    )
    session.add(profile)
    session.commit()

    body = EpisodeDownloadAPICreate(local_media_profile_id=profile.id)
    download = create_episode_download(session, episode.slug, body)
    session.commit()
    assert download.artifact_status == MediaDownloadArtifactStatus.ABSENT.value
    assert download.file_path.endswith("test-episode-101.ext")

    # Second request for the same profile reuses the row instead of duplicating it
    again = create_episode_download(session, episode.slug, body)
    session.commit()
    assert again.id == download.id

    # A downloaded file is a conflict (one download per profile)
    monkeypatch.setattr(
        "backend.api.endpoints.media_downloads.service._reconcile_existing_artifact",
        lambda s, existing: None,
    )
    mark_artifact_available(download)
    session.commit()
    with pytest.raises(HTTPException) as exc_info:
        create_episode_download(session, episode.slug, body)
    assert exc_info.value.status_code == 409

    session.close()
    engine.dispose()


# ---------- ffmpeg remux ----------

def test_remux_to_mp4_runs_ffmpeg_and_renames_part_file(tmp_path, monkeypatch):
    from dailywire_downloader import ffmpeg as ffmpeg_module

    calls = []

    def fake_which(path):
        return "/usr/bin/ffmpeg"

    class FakeCompleted:
        returncode = 0
        stdout = ""

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        # Simulate ffmpeg writing the .part output file
        part_path = cmd[-1]
        with open(part_path, "wb") as f:
            f.write(b"fake-mp4-data")
        return FakeCompleted()

    monkeypatch.setattr(ffmpeg_module.shutil, "which", fake_which)
    monkeypatch.setattr(ffmpeg_module.subprocess, "run", fake_run)

    src = tmp_path / "raw.ts"
    src.write_bytes(b"fake-ts-data")
    dest = tmp_path / "final.mp4"

    ffmpeg_module.remux_to_mp4(str(src), str(dest))

    assert dest.exists()
    assert not (tmp_path / "final.mp4.part").exists()
    assert calls[0][0] == "ffmpeg"
    assert "-i" in calls[0] and calls[0][calls[0].index("-i") + 1] == str(src)
    # The flags that fix the HLS-TS-to-MP4 remux failures actually seen
    assert "+genpts" in calls[0]
    assert "-bsf:a" in calls[0] and "aac_adtstoasc" in calls[0]
    # The real bug: ffmpeg picks the muxer from the output filename's own
    # extension, and that's "<dest>.part" - an extension it can't map to any
    # muxer. "-f mp4" forces it explicitly instead of guessing wrong.
    assert "-f" in calls[0] and calls[0][calls[0].index("-f") + 1] == "mp4"
    assert str(src) in calls[0]
    assert str(dest) not in calls[0]  # ffmpeg wrote the .part path, not dest directly


def test_remux_to_mp4_raises_when_ffmpeg_missing(monkeypatch, tmp_path):
    from dailywire_downloader import ffmpeg as ffmpeg_module
    from dailywire_downloader.errors import FfmpegNotFoundError

    monkeypatch.setattr(ffmpeg_module.shutil, "which", lambda path: None)

    with pytest.raises(FfmpegNotFoundError):
        ffmpeg_module.remux_to_mp4(str(tmp_path / "a.ts"), str(tmp_path / "b.mp4"))


def test_remux_to_mp4_cleans_up_part_file_on_failure(monkeypatch, tmp_path):
    from dailywire_downloader import ffmpeg as ffmpeg_module
    from dailywire_downloader.errors import DownloadError

    monkeypatch.setattr(ffmpeg_module.shutil, "which", lambda path: "/usr/bin/ffmpeg")

    class FakeFailed:
        returncode = 1
        stdout = "boom"

    def fake_run(cmd, **kwargs):
        part_path = cmd[-1]
        with open(part_path, "wb") as f:
            f.write(b"partial")
        return FakeFailed()

    monkeypatch.setattr(ffmpeg_module.subprocess, "run", fake_run)

    dest = tmp_path / "final.mp4"
    with pytest.raises(DownloadError, match="boom"):
        ffmpeg_module.remux_to_mp4(str(tmp_path / "raw.ts"), str(dest))

    assert not dest.exists()
    assert not (tmp_path / "final.mp4.part").exists()


def test_remux_to_mp4_error_uses_tail_lines_not_a_raw_character_slice(monkeypatch, tmp_path):
    """A raw character slice of long ffmpeg output can land mid-line (this is
    literally what was reported: a chunk of the multi-line "configuration:"
    banner with no visible error). Lines are the unit that must be kept."""
    from dailywire_downloader import ffmpeg as ffmpeg_module
    from dailywire_downloader.errors import DownloadError

    monkeypatch.setattr(ffmpeg_module.shutil, "which", lambda path: "/usr/bin/ffmpeg")

    noise = "\n".join(f"configuration line {i} " + "x" * 80 for i in range(50))
    real_error = "[mp4 @ 0x0] Malformed AAC bitstream detected, use audio bitstream filter 'aac_adtstoasc' to fix it"

    class FakeFailed:
        returncode = 234
        stdout = f"{noise}\n{real_error}\n"

    monkeypatch.setattr(ffmpeg_module.subprocess, "run", lambda cmd, **kwargs: FakeFailed())

    with pytest.raises(DownloadError) as exc_info:
        ffmpeg_module.remux_to_mp4(str(tmp_path / "raw.ts"), str(tmp_path / "final.mp4"))

    assert real_error in str(exc_info.value)
    assert "configuration line 0 " not in str(exc_info.value)


def test_remux_to_mp4_strips_ffmpeg_banner_even_when_output_is_short(monkeypatch, tmp_path):
    """The actual failure reported: ffmpeg's own banner (version, "built with",
    the huge "configuration:" line, lib version lines) is short enough in total
    that a plain last-N-lines tail still included it wholesale, burying the one
    real diagnostic line under noise. The banner must be dropped outright, not
    just hoped to fall outside the tail window."""
    from dailywire_downloader import ffmpeg as ffmpeg_module
    from dailywire_downloader.errors import DownloadError

    monkeypatch.setattr(ffmpeg_module.shutil, "which", lambda path: "/usr/bin/ffmpeg")

    huge_configuration_line = "configuration: " + " ".join(f"--enable-lib{i}" for i in range(60))
    real_error = "[mp4 @ 0x0] Malformed AAC bitstream detected, use audio bitstream filter 'aac_adtstoasc' to fix it"
    banner = "\n".join([
        "ffmpeg version 8.0.1 Copyright (c) 2000-2025 the FFmpeg developers",
        "built with Apple clang version 16.0.0 (clang-1600.0.26.6)",
        huge_configuration_line,
        "libavutil      60.  8.100 / 60.  8.100",
        "libavcodec     62. 11.100 / 62. 11.100",
        "libavformat    62.  3.100 / 62.  3.100",
    ])

    class FakeFailed:
        returncode = 234
        stdout = f"{banner}\n{real_error}\n"

    monkeypatch.setattr(ffmpeg_module.subprocess, "run", lambda cmd, **kwargs: FakeFailed())

    with pytest.raises(DownloadError) as exc_info:
        ffmpeg_module.remux_to_mp4(str(tmp_path / "raw.ts"), str(tmp_path / "final.mp4"))

    message = str(exc_info.value)
    assert real_error in message
    assert "configuration:" not in message
    assert "ffmpeg version" not in message
