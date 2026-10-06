from __future__ import annotations

import pytest


def test_video_fallback_for_audio_selects_smallest_rendition_and_m4a(monkeypatch):
    from dailywire_downloader.models import MediaInfo, MediaKind, VideoRendition
    from dailywire_downloader import source as source_module

    info = MediaInfo(
        url="https://media.test/master.m3u8",
        kind=MediaKind.HLS_MASTER,
        renditions=(
            VideoRendition("https://media.test/1080.m3u8", 1920, 1080, 4_000_000, "avc1,mp4a"),
            VideoRendition("https://media.test/270.m3u8", 480, 270, 600_000, "avc1,mp4a"),
            VideoRendition("https://media.test/720.m3u8", 1280, 720, 2_000_000, "avc1,mp4a"),
        ),
    )
    monkeypatch.setattr(source_module, "probe", lambda _url: info)

    source = source_module.resolve_download_source(
        info.url,
        preferred_format="format_audio_only",
        audio_only=True,
        remux_video_to_mp4=True,
        video_fallback_for_audio=True,
    )

    assert source.url == "https://media.test/270.m3u8"
    assert source.format_downloaded == "audio"
    assert source.use_hls is True
    assert source.remux_to_mp4 is False
    assert source.convert_video_to_m4a is True
    assert source.extension == "m4a"
    assert source.audio_only is True


def test_audio_fallback_conversion_is_planned_between_transfer_and_embedding(tmp_path):
    from dailywire_downloader.plan import ResolvedDownloadSource, build_download_plan

    plan = build_download_plan(
        source=ResolvedDownloadSource(
            "https://media.test/270.m3u8",
            "audio",
            True,
            False,
            "m4a",
            True,
            convert_video_to_m4a=True,
        ),
        requested_destination=tmp_path / "library" / "Episode.m4a",
        download_mode="temporary",
        temporary_root=tmp_path / "temporary",
        metadata_tags=(("title", "Episode"),),
    )

    assert plan.stage("convert_audio").code == "convert_audio"
    assert plan.stage("convert_audio").depends_on == ("media",)
    assert plan.stage("convert_audio").weight == pytest.approx(0.08)
    assert plan.stage("embed").depends_on == ("convert_audio",)
    assert plan.stage("publish").depends_on == ("embed",)


def test_convert_video_to_m4a_stream_copies_audio(tmp_path, monkeypatch):
    from dailywire_downloader import ffmpeg as ffmpeg_module

    calls = []
    monkeypatch.setattr(ffmpeg_module.shutil, "which", lambda _path: "/usr/bin/ffmpeg")

    class Completed:
        returncode = 0
        stdout = ""

    def fake_run(command, **_kwargs):
        calls.append(command)
        with open(command[-1], "wb") as output:
            output.write(b"m4a")
        return Completed()

    monkeypatch.setattr(ffmpeg_module.subprocess, "run", fake_run)

    source = tmp_path / "video.ts"
    source.write_bytes(b"video")
    destination = tmp_path / "audio.m4a"

    ffmpeg_module.convert_video_to_m4a(str(source), str(destination))

    command = calls[0]
    assert command[command.index("-map") + 1] == "0:a:0"
    assert "-vn" in command
    assert command[command.index("-c:a") + 1] == "copy"
    assert command[command.index("-f") + 1] == "mp4"
    assert destination.read_bytes() == b"m4a"
    assert not (tmp_path / "audio.m4a.part").exists()
