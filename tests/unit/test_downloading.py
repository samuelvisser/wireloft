from __future__ import annotations

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
    # The huge banner line must not survive even after the outer 1000-char cap
    # applied when this becomes a stored error_message.
    from task_manager.tasks.workers.download_episode.service import _truncate_message
    assert real_error in _truncate_message(message)


# ---------- video downloads remux end-to-end ----------

def _db_with_episode_and_download(video_local_media_profile=True):
    from backend.db.models import EpisodeMediaDownload, LocalMediaProfile
    from backend.types.download_profile_types import MediaDownloadStatus
    from backend.types.media_types import MediaType

    session, engine, episode = _db_with_episode()

    profile = LocalMediaProfile(
        slug="video-1080p" if video_local_media_profile else "audio",
        name="Video 1080p" if video_local_media_profile else "Audio",
        output_template="/downloads/{show}/{episode}.ext",
        preferred_format="format_1080p" if video_local_media_profile else "format_audio_only",
    )
    session.add(profile)
    session.flush()

    episode.video_url = "https://example.test/master.m3u8"
    episode.audio_url = "https://example.test/audio.m4a"

    download = EpisodeMediaDownload(
        type=MediaType.EPISODE.value,
        media_item_id=episode.id,
        local_media_profile_id=profile.id,
        download_status=MediaDownloadStatus.PENDING.value,
        file_path="/downloads/pending.ext",
        progress=0,
    )
    session.add(download)
    session.commit()
    return session, engine, episode, download


def test_retry_active_download_starts_new_generation_and_records_cancellation():
    from backend.api.endpoints.media_downloads.service import retry_media_download
    from backend.db.models.media_download import MediaDownloadAttempt

    session, engine, _episode, download = _db_with_episode_and_download(
        video_local_media_profile=False,
    )
    download.download_status = "downloading"
    download.progress = 42
    download.downloaded_bytes = 1234
    session.commit()

    original_generation = download.attempt_generation
    restarted = retry_media_download(session, download.id)
    session.commit()

    assert restarted.id == download.id
    assert restarted.attempt_generation == original_generation + 1
    assert restarted.download_status == "pending"
    assert restarted.progress == 0
    assert restarted.downloaded_bytes is None
    [attempt] = session.query(MediaDownloadAttempt).all()
    assert attempt.status == "cancelled"
    assert attempt.error_message == "Cancelled by the user and restarted"
    assert attempt.downloaded_bytes == 1234

    session.close()
    engine.dispose()


def test_replaced_episode_worker_cancels_without_overwriting_fresh_state(tmp_path, monkeypatch):
    from sqlalchemy.orm import sessionmaker

    from config import get_settings
    from dailywire_downloader import DownloadCancelled, MediaInfo, MediaKind
    from task_manager.tasks.workers import download_attempt
    from task_manager.tasks.workers.download_episode import service
    from task_manager.tasks.workers.download_profile_worker import _helpers as profile_helpers

    session, engine, episode, download = _db_with_episode_and_download(
        video_local_media_profile=False,
    )
    session_factory = sessionmaker(bind=engine)
    monkeypatch.setattr(download_attempt, "get_session", session_factory)
    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)
    monkeypatch.setattr(
        service,
        "probe",
        lambda url: MediaInfo(url=url, kind=MediaKind.DIRECT_FILE, content_type="audio/mp4"),
    )

    original_generation = download.attempt_generation

    def cancel_during_download(url, dest_path, *, progress=None, should_cancel=None):
        with session_factory() as other_session:
            current = other_session.get(type(download), download.id)
            current.attempt_generation += 1
            current.download_status = "pending"
            current.progress = 0
            other_session.commit()
        assert should_cancel is not None
        should_cancel.ensure_current()

    monkeypatch.setattr(service, "download_file", cancel_during_download)
    drained = Mock()
    monkeypatch.setattr(profile_helpers, "trigger_next_pending_downloads", drained)

    with pytest.raises(DownloadCancelled):
        asyncio.run(service.run_download_episode(
            session,
            media_download_id=download.id,
            attempt_generation=original_generation,
        ))

    session.expire_all()
    refreshed = session.get(type(download), download.id)
    assert refreshed.attempt_generation == original_generation + 1
    assert refreshed.download_status == "pending"
    assert refreshed.progress == 0
    drained.assert_not_called()

    session.close()
    engine.dispose()


def test_run_download_episode_remuxes_hls_video_to_mp4(tmp_path, monkeypatch):
    from config import get_settings
    from dailywire_downloader import DownloadResult, MediaInfo, MediaKind, VideoRendition
    from task_manager.tasks.workers.download_episode import service

    session, engine, episode, download = _db_with_episode_and_download()
    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)
    monkeypatch.setattr(get_settings().download_settings, "remux_video_to_mp4", True)

    master_info = MediaInfo(
        url=episode.video_url,
        kind=MediaKind.HLS_MASTER,
        renditions=(VideoRendition(url="https://example.test/1080/rendition.m3u8", width=1920, height=1080, bandwidth=1000, codecs=None),),
    )
    monkeypatch.setattr(service, "probe", lambda url: master_info)

    hls_calls = []
    remux_calls = []

    def fake_download_hls(url, dest_path, *, progress=None, should_cancel=None):
        hls_calls.append((url, dest_path))
        __import__("os").makedirs(__import__("os").path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(b"raw-ts-bytes")
        return DownloadResult(path=dest_path, bytes_downloaded=12, segments_downloaded=3)

    def fake_remux_to_mp4(src_path, dest_path, *, ffmpeg_path="ffmpeg", should_cancel=None):
        remux_calls.append((src_path, dest_path, ffmpeg_path))
        with open(dest_path, "wb") as f:
            f.write(b"remuxed-mp4-bytes")

    monkeypatch.setattr(service, "download_hls", fake_download_hls)
    monkeypatch.setattr(service, "remux_to_mp4", fake_remux_to_mp4)

    asyncio.run(service.run_download_episode(session, media_download_id=download.id))

    session.refresh(download)
    assert download.file_path.endswith(".mp4")
    assert download.download_status == "downloaded"
    assert download.format_downloaded == "1920x1080"

    assert len(hls_calls) == 1
    raw_ts_path = hls_calls[0][1]
    assert raw_ts_path.endswith(".mp4.rawts")
    assert len(remux_calls) == 1
    assert remux_calls[0][0] == raw_ts_path
    assert remux_calls[0][1] == download.file_path

    # The temporary raw .ts file must be cleaned up, only the final .mp4 remains
    assert not __import__("os").path.exists(raw_ts_path)
    assert __import__("os").path.exists(download.file_path)

    session.close()
    engine.dispose()


def test_run_download_episode_keeps_ts_when_remux_disabled(tmp_path, monkeypatch):
    from config import get_settings
    from dailywire_downloader import DownloadResult, MediaInfo, MediaKind, VideoRendition
    from task_manager.tasks.workers.download_episode import service

    session, engine, episode, download = _db_with_episode_and_download()
    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)
    monkeypatch.setattr(get_settings().download_settings, "remux_video_to_mp4", False)

    master_info = MediaInfo(
        url=episode.video_url,
        kind=MediaKind.HLS_MASTER,
        renditions=(VideoRendition(url="https://example.test/1080/rendition.m3u8", width=1920, height=1080, bandwidth=1000, codecs=None),),
    )
    monkeypatch.setattr(service, "probe", lambda url: master_info)

    remux_calls = []
    monkeypatch.setattr(service, "remux_to_mp4", lambda *a, **k: remux_calls.append((a, k)))

    def fake_download_hls(url, dest_path, *, progress=None, should_cancel=None):
        __import__("os").makedirs(__import__("os").path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(b"raw-ts-bytes")
        return DownloadResult(path=dest_path, bytes_downloaded=12, segments_downloaded=3)

    monkeypatch.setattr(service, "download_hls", fake_download_hls)

    asyncio.run(service.run_download_episode(session, media_download_id=download.id))

    session.refresh(download)
    assert download.file_path.endswith(".ts")
    assert download.download_status == "downloaded"
    assert remux_calls == []

    session.close()
    engine.dispose()


def test_run_download_episode_audio_unaffected_by_remux_setting(tmp_path, monkeypatch):
    from config import get_settings
    from dailywire_downloader import DownloadResult, MediaInfo, MediaKind
    from task_manager.tasks.workers.download_episode import service

    session, engine, episode, download = _db_with_episode_and_download(video_local_media_profile=False)
    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)
    monkeypatch.setattr(get_settings().download_settings, "remux_video_to_mp4", True)

    audio_info = MediaInfo(url=episode.audio_url, kind=MediaKind.DIRECT_FILE, content_type="audio/mp4")
    monkeypatch.setattr(service, "probe", lambda url: audio_info)

    remux_calls = []
    monkeypatch.setattr(service, "remux_to_mp4", lambda *a, **k: remux_calls.append((a, k)))

    def fake_download_file(url, dest_path, *, progress=None, should_cancel=None):
        __import__("os").makedirs(__import__("os").path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(b"audio-bytes")
        from dailywire_downloader import DownloadResult
        return DownloadResult(path=dest_path, bytes_downloaded=11)

    monkeypatch.setattr(service, "download_file", fake_download_file)

    asyncio.run(service.run_download_episode(session, media_download_id=download.id))

    session.refresh(download)
    assert download.file_path.endswith(".m4a")
    assert remux_calls == []

    session.close()
    engine.dispose()


# ---------- queue draining after completion ----------

def test_run_download_episode_drains_next_pending_download_on_success(tmp_path, monkeypatch):
    from config import get_settings
    from dailywire_downloader import DownloadResult, MediaInfo, MediaKind
    from task_manager.tasks.workers.download_episode import service
    from task_manager.tasks.workers.download_profile_worker import _helpers as profile_helpers

    session, engine, episode, download = _db_with_episode_and_download(video_local_media_profile=False)
    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)

    audio_info = MediaInfo(url=episode.audio_url, kind=MediaKind.DIRECT_FILE, content_type="audio/mp4")
    monkeypatch.setattr(service, "probe", lambda url: audio_info)

    def fake_download_file(url, dest_path, *, progress=None, should_cancel=None):
        __import__("os").makedirs(__import__("os").path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(b"audio-bytes")
        return DownloadResult(path=dest_path, bytes_downloaded=11)

    monkeypatch.setattr(service, "download_file", fake_download_file)

    drained = Mock()
    monkeypatch.setattr(profile_helpers, "trigger_next_pending_downloads", drained)

    asyncio.run(service.run_download_episode(session, media_download_id=download.id))

    session.refresh(download)
    assert download.download_status == "downloaded"
    drained.assert_called_once_with(session)

    session.close()
    engine.dispose()


def test_run_download_episode_drains_next_pending_download_on_failure(tmp_path, monkeypatch):
    from config import get_settings
    from task_manager.tasks.workers.download_episode import service
    from task_manager.tasks.workers.download_profile_worker import _helpers as profile_helpers

    session, engine, episode, download = _db_with_episode_and_download(video_local_media_profile=False)
    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)

    def broken_probe(url):
        raise RuntimeError("network is down")

    monkeypatch.setattr(service, "probe", broken_probe)

    drained = Mock()
    monkeypatch.setattr(profile_helpers, "trigger_next_pending_downloads", drained)

    with pytest.raises(RuntimeError, match="network is down"):
        asyncio.run(service.run_download_episode(session, media_download_id=download.id))

    session.refresh(download)
    assert download.download_status == "error"
    # A failed download frees its own concurrency slot just as much as a
    # successful one, so the queue must still be backfilled.
    drained.assert_called_once_with(session)

    session.close()
    engine.dispose()


# ---------- is_redownload_attempt persists regardless of outcome ----------

def test_run_download_episode_records_redownload_attempt_on_success(tmp_path, monkeypatch):
    from config import get_settings
    from dailywire_downloader import DownloadResult, MediaInfo, MediaKind
    from task_manager.tasks.workers.download_episode import service

    session, engine, episode, download = _db_with_episode_and_download(video_local_media_profile=False)
    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)

    audio_info = MediaInfo(url=episode.audio_url, kind=MediaKind.DIRECT_FILE, content_type="audio/mp4")
    monkeypatch.setattr(service, "probe", lambda url: audio_info)

    def fake_download_file(url, dest_path, *, progress=None, should_cancel=None):
        __import__("os").makedirs(__import__("os").path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(b"audio-bytes")
        return DownloadResult(path=dest_path, bytes_downloaded=11)

    monkeypatch.setattr(service, "download_file", fake_download_file)

    asyncio.run(service.run_download_episode(session, media_download_id=download.id, is_redownload=True))

    session.refresh(download)
    assert download.download_status == "redownloaded"
    assert download.is_redownload_attempt is True

    session.close()
    engine.dispose()


def test_run_download_episode_records_redownload_attempt_on_failure(tmp_path, monkeypatch):
    from config import get_settings
    from task_manager.tasks.workers.download_episode import service

    session, engine, episode, download = _db_with_episode_and_download(video_local_media_profile=False)
    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)

    monkeypatch.setattr(service, "probe", lambda url: (_ for _ in ()).throw(RuntimeError("boom")))

    with pytest.raises(RuntimeError):
        asyncio.run(service.run_download_episode(session, media_download_id=download.id, is_redownload=True))

    session.refresh(download)
    assert download.download_status == "error"
    # Recorded up front, so it survives even though the attempt itself failed.
    assert download.is_redownload_attempt is True

    session.close()
    engine.dispose()


def test_run_download_episode_records_initial_attempt(tmp_path, monkeypatch):
    from config import get_settings
    from dailywire_downloader import DownloadResult, MediaInfo, MediaKind
    from task_manager.tasks.workers.download_episode import service

    session, engine, episode, download = _db_with_episode_and_download(video_local_media_profile=False)
    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)

    audio_info = MediaInfo(url=episode.audio_url, kind=MediaKind.DIRECT_FILE, content_type="audio/mp4")
    monkeypatch.setattr(service, "probe", lambda url: audio_info)

    def fake_download_file(url, dest_path, *, progress=None, should_cancel=None):
        __import__("os").makedirs(__import__("os").path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(b"audio-bytes")
        return DownloadResult(path=dest_path, bytes_downloaded=11)

    monkeypatch.setattr(service, "download_file", fake_download_file)

    asyncio.run(service.run_download_episode(session, media_download_id=download.id))

    session.refresh(download)
    assert download.is_redownload_attempt is False

    session.close()
    engine.dispose()


# ---------- download ledger: previous attempts survive a retry ----------

def test_run_download_episode_appends_ledger_entry_on_success(tmp_path, monkeypatch):
    from config import get_settings
    from dailywire_downloader import DownloadResult, MediaInfo, MediaKind
    from task_manager.tasks.workers.download_episode import service
    from backend.db.models.media_download import MediaDownloadAttempt

    session, engine, episode, download = _db_with_episode_and_download(video_local_media_profile=False)
    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)

    audio_info = MediaInfo(url=episode.audio_url, kind=MediaKind.DIRECT_FILE, content_type="audio/mp4")
    monkeypatch.setattr(service, "probe", lambda url: audio_info)

    def fake_download_file(url, dest_path, *, progress=None, should_cancel=None):
        __import__("os").makedirs(__import__("os").path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(b"audio-bytes")
        return DownloadResult(path=dest_path, bytes_downloaded=11)

    monkeypatch.setattr(service, "download_file", fake_download_file)

    asyncio.run(service.run_download_episode(session, media_download_id=download.id))

    [entry] = session.query(MediaDownloadAttempt).filter_by(media_download_id=download.id).all()
    assert entry.status == "downloaded"
    assert entry.is_redownload is False
    assert entry.error_message is None
    assert entry.downloaded_bytes == 11
    assert entry.started_at is not None and entry.finished_at is not None

    session.close()
    engine.dispose()


def test_run_download_episode_appends_ledger_entry_on_failure_and_survives_a_retry(tmp_path, monkeypatch):
    """The exact bug reported: a retry clears download.error_message so the
    live row shows "no errors" again while it re-downloads, but the previous
    error must still be readable from the ledger."""
    from config import get_settings
    from dailywire_downloader import DownloadResult, MediaInfo, MediaKind
    from task_manager.tasks.workers.download_episode import service
    from backend.db.models.media_download import MediaDownloadAttempt

    session, engine, episode, download = _db_with_episode_and_download(video_local_media_profile=False)
    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)

    monkeypatch.setattr(service, "probe", lambda url: (_ for _ in ()).throw(RuntimeError("ffmpeg exploded")))

    with pytest.raises(RuntimeError):
        asyncio.run(service.run_download_episode(session, media_download_id=download.id))

    session.refresh(download)
    assert download.error_message and "ffmpeg exploded" in download.error_message

    # Simulate a retry: the row's own error is cleared before the next attempt,
    # exactly like the live row does while re-downloading.
    download.download_status = "pending"
    download.error_message = None
    session.commit()

    [entry] = session.query(MediaDownloadAttempt).filter_by(media_download_id=download.id).all()
    assert entry.status == "error"
    assert entry.is_redownload is False
    assert "ffmpeg exploded" in entry.error_message

    session.close()
    engine.dispose()


def test_run_download_episode_ledger_keeps_every_attempt_across_retries(tmp_path, monkeypatch):
    from config import get_settings
    from dailywire_downloader import DownloadResult, MediaInfo, MediaKind
    from task_manager.tasks.workers.download_episode import service
    from backend.db.models.media_download import MediaDownloadAttempt

    session, engine, episode, download = _db_with_episode_and_download(video_local_media_profile=False)
    monkeypatch.setattr(get_settings().download_settings, "download_root", tmp_path)

    monkeypatch.setattr(service, "probe", lambda url: (_ for _ in ()).throw(RuntimeError("first failure")))
    with pytest.raises(RuntimeError):
        asyncio.run(service.run_download_episode(session, media_download_id=download.id))

    audio_info = MediaInfo(url=episode.audio_url, kind=MediaKind.DIRECT_FILE, content_type="audio/mp4")
    monkeypatch.setattr(service, "probe", lambda url: audio_info)

    def fake_download_file(url, dest_path, *, progress=None, should_cancel=None):
        __import__("os").makedirs(__import__("os").path.dirname(dest_path), exist_ok=True)
        with open(dest_path, "wb") as f:
            f.write(b"audio-bytes")
        return DownloadResult(path=dest_path, bytes_downloaded=11)

    monkeypatch.setattr(service, "download_file", fake_download_file)
    asyncio.run(service.run_download_episode(session, media_download_id=download.id))

    entries = (
        session.query(MediaDownloadAttempt)
        .filter_by(media_download_id=download.id)
        .order_by(MediaDownloadAttempt.id)
        .all()
    )
    assert [e.status for e in entries] == ["error", "downloaded"]
    assert "first failure" in entries[0].error_message
    assert entries[1].error_message is None

    session.close()
    engine.dispose()


# ---------- media-download-attempts endpoint ----------

def test_get_media_download_attempts_returns_newest_first():
    from backend.api.endpoints.media_downloads.service import get_media_download_attempts
    from backend.db.models.media_download import MediaDownloadAttempt

    session, engine, episode, download = _db_with_episode_and_download(video_local_media_profile=False)
    session.add_all([
        MediaDownloadAttempt(media_download_id=download.id, is_redownload=False, status="error", error_message="first"),
        MediaDownloadAttempt(media_download_id=download.id, is_redownload=False, status="downloaded", error_message=None),
    ])
    session.commit()

    attempts = get_media_download_attempts(session, download.id)
    assert [a.status for a in attempts] == ["downloaded", "error"]
    assert attempts[1].error_message == "first"

    session.close()
    engine.dispose()


def test_get_media_download_attempts_404s_for_missing_download():
    from fastapi import HTTPException

    from backend.api.endpoints.media_downloads.service import get_media_download_attempts

    session, engine, episode, download = _db_with_episode_and_download(video_local_media_profile=False)

    with pytest.raises(HTTPException) as exc_info:
        get_media_download_attempts(session, download.id + 999)
    assert exc_info.value.status_code == 404

    session.close()
    engine.dispose()


# ---------- error message truncation ----------

def test_truncate_message_keeps_the_end_not_the_start():
    from task_manager.tasks.workers.download_episode.service import _truncate_message

    short = "boom"
    assert _truncate_message(short) == short

    # The real diagnostic content sits right at the end, well within the last
    # 1000 characters; a head slice (message[:1000]) would miss it entirely.
    long_message = "A" * 2000 + "THE REAL ERROR IS HERE"
    truncated = _truncate_message(long_message, limit=1000)
    assert len(truncated) <= 1000
    assert truncated.endswith("THE REAL ERROR IS HERE")
    assert truncated != long_message[:1000]

    # The default limit is generous: this is the full text a download's log
    # shows, not the compact table row, so a merely-long message survives whole.
    assert _truncate_message(long_message) == long_message


# ---------- download log fields surfaced via the API view ----------

def test_media_downloads_view_exposes_redownload_and_version_fields():
    from backend.api.endpoints.media_downloads.service import get_media_downloads_view

    session, engine, episode, download = _db_with_episode_and_download(video_local_media_profile=False)
    download.is_redownload_attempt = True
    download.downloaded_publish_status = "published_final"
    download.error_message = "boom"
    session.commit()

    [view] = get_media_downloads_view(session)
    assert view.is_redownload_attempt is True
    assert view.downloaded_publish_status == "published_final"
    assert view.error_message == "boom"

    session.close()
    engine.dispose()
