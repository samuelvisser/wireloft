from __future__ import annotations

from types import SimpleNamespace

import pytest

from dailywire_downloader.hls import parse_subtitle_renditions
from dailywire_downloader.models import MediaKind, SubtitleRendition, VideoRendition
from dailywire_downloader.plan import ResolvedDownloadSource, SidecarSpec, build_download_plan
from dailywire_downloader.subtitles import download_hls_webvtt


_MASTER = """#EXTM3U
#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="sub1",NAME="English (Generated)",LANGUAGE="en",URI="subs/en.m3u8",FORCED=NO
#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="sub1",NAME="French",LANGUAGE="fr",URI="subs/fr.m3u8"
#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="sub1",NAME="English Forced",LANGUAGE="en",URI="subs/en-forced.m3u8",FORCED=YES
#EXT-X-MEDIA:TYPE=SUBTITLES,GROUP-ID="other",NAME="Unused",LANGUAGE="de",URI="subs/de.m3u8"
#EXT-X-STREAM-INF:BANDWIDTH=100000,RESOLUTION=1920x1080,SUBTITLES="sub1"
video.m3u8
"""


def test_hls_master_discovers_languages_and_media_server_sidecar_names():
    tracks = parse_subtitle_renditions(_MASTER, "https://cdn.example/master.m3u8?token=secret")

    assert [(track.language, track.forced, track.target_suffix) for track in tracks] == [
        ("en", False, ".en.srt"),
        ("fr", False, ".fr.srt"),
        ("en", True, ".en.forced.srt"),
    ]
    assert tracks[0].url == "https://cdn.example/subs/en.m3u8"


def test_master_probe_preserves_subtitle_renditions(monkeypatch):
    from dailywire_downloader import downloader

    class Response:
        headers = {"Content-Type": "application/vnd.apple.mpegurl"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return _MASTER.encode()

    monkeypatch.setattr(downloader, "http_get", lambda _url: Response())
    info = downloader.probe("https://cdn.example/master.m3u8")

    assert info.kind is MediaKind.HLS_MASTER
    assert info.subtitles[0].target_suffix == ".en.srt"
    assert len(info.renditions) == 1


def _fake_subtitle_http(monkeypatch, segment_texts: tuple[str, str]):
    import dailywire_downloader.subtitles as module

    manifest = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-TARGETDURATION:6
#EXTINF:6.0,
segment0.vtt
#EXTINF:6.0,
segment1.vtt
#EXT-X-ENDLIST
"""
    urls = {
        "https://cdn.example/subs.m3u8": manifest.encode(),
        "https://cdn.example/segment0.vtt": segment_texts[0].encode(),
        "https://cdn.example/segment1.vtt": segment_texts[1].encode(),
    }

    class Response:
        def __init__(self, data: bytes):
            self.data = data

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def iter_chunks(self, _chunk_size):
            yield self.data

    monkeypatch.setattr(module, "http_get", lambda url: Response(urls[url]))


def test_segmented_webvtt_timestamp_maps_produce_synchronized_srt(monkeypatch):
    _fake_subtitle_http(monkeypatch, (
        """WEBVTT
X-TIMESTAMP-MAP=LOCAL:00:00:00.000,MPEGTS:900000

00:00:01.000 --> 00:00:02.000
<b>Hello</b>
""",
        """WEBVTT
X-TIMESTAMP-MAP=LOCAL:00:00:00.000,MPEGTS:1440000

00:00:01.000 --> 00:00:02.000
World
""",
    ))

    result = download_hls_webvtt(
        "https://cdn.example/subs.m3u8",
        maximum_bytes=100000, should_cancel=lambda: False,
    ).decode()

    assert "00:00:01,000 --> 00:00:02,000\nHello" in result
    assert "00:00:07,000 --> 00:00:08,000\nWorld" in result
    assert "X-TIMESTAMP-MAP" not in result
    assert "WEBVTT" not in result


@pytest.mark.parametrize("second_time,expected_time", [
    ("00:00:07.000", "00:00:07,000"),  # already on the media timeline
    ("00:00:01.000", "00:00:07,000"),  # segment-relative fallback
])
def test_webvtt_without_maps_uses_global_or_segment_relative_timing(
    monkeypatch, second_time, expected_time,
):
    _fake_subtitle_http(monkeypatch, (
        "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nFirst\n",
        f"WEBVTT\n\n{second_time} --> 00:00:08.000\nSecond\n"
        if second_time.endswith(":07.000")
        else "WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nSecond\n",
    ))
    result = download_hls_webvtt(
        "https://cdn.example/subs.m3u8",
        maximum_bytes=100000, should_cancel=lambda: False,
    ).decode()
    assert f"{expected_time} --> 00:00:08,000\nSecond" in result


def test_download_plan_uses_existing_sidecar_and_embedding_stages(tmp_path):
    asset = SidecarSpec(
        "subtitle_0", "subtitle", url="https://cdn.example/subs.m3u8",
        extension="srt", target_suffix=".en.srt", source_format="hls_webvtt",
        language="en", required=False, publish=True,
    )
    plan = build_download_plan(
        source=ResolvedDownloadSource(
            "https://cdn.example/video.m3u8", "1920x1080", True, True, "mp4", False,
        ),
        requested_destination=tmp_path / "Movie.mp4", temporary_root=tmp_path / "temp",
        download_mode="temporary", assets=(asset,),
        subtitle_asset_ids=("subtitle_0",),
    )

    assert plan.stage("embed").code == "embed_subtitles"
    assert "acquire:subtitle_0" in plan.stage("embed").depends_on
    assert "embed" in plan.stage("publish").depends_on
    assert plan.stage("publish:subtitle_0").code == "publish_sidecar"
    assert plan.subtitle_asset_ids == ("subtitle_0",)


def test_movie_profiles_default_to_subtitle_sidecars():
    from backend.api.models.movie_local_media_profile import MovieLocalMediaProfileAPICreate

    movie = MovieLocalMediaProfileAPICreate(
        name="Movie", type="movie", preferred_format="format_1080p",
        output_template="/downloads/movies/{{ movie_title }}/{{ title }}.ext",
    )
    assert movie.subtitle_mode == "sidecar"


@pytest.mark.parametrize(("scope", "expected"), [
    ("both", "sidecar"),
    ("series", "sidecar"),
    ("podcast", "no_subtitles"),
])
def test_show_subtitle_default_follows_scope_when_not_specified(scope, expected):
    from backend.api.models.show_local_media_profile import ShowLocalMediaProfileAPICreate

    show = ShowLocalMediaProfileAPICreate(
        name="Show", type="show", show_scope=scope,
        preferred_format="format_1080p",
        output_template="/downloads/shows/{{ show }}/{{ episode }}.ext",
    )
    assert show.subtitle_mode == expected
    assert show.model_dump(by_alias=True, mode="json")["subtitle_mode"] == expected


@pytest.mark.parametrize("mode", [
    "no_subtitles", "embed", "sidecar", "embed_and_sidecar",
])
@pytest.mark.parametrize("scope", ["podcast", "series", "both"])
def test_manual_subtitle_selection_overrides_show_scope(scope, mode):
    from backend.api.models.show_local_media_profile import ShowLocalMediaProfileAPICreate

    profile = ShowLocalMediaProfileAPICreate(
        name="Show", preferred_format="format_1080p",
        show_scope=scope, subtitle_mode=mode,
        output_template="/downloads/shows/{{ show }}/{{ episode }}.ext",
    )
    assert profile.subtitle_mode == mode


def test_subtitle_system_mode_is_no_longer_valid():
    from pydantic import ValidationError
    from backend.api.models.show_local_media_profile import ShowLocalMediaProfileAPICreate

    with pytest.raises(ValidationError):
        ShowLocalMediaProfileAPICreate(
            name="Show", preferred_format="format_1080p", subtitle_mode="system",
            output_template="/downloads/shows/{{ show }}/{{ episode }}.ext",
        )


def test_system_settings_no_longer_expose_subtitle_mode():
    from backend.api.models.settings import SettingsValues
    from config.settings.settings import AppSettings

    settings = AppSettings()
    assert "subtitle_mode" not in type(settings.download_settings).model_fields
    serialized = SettingsValues.from_app_settings(settings).model_dump(
        by_alias=True, mode="json",
    )
    assert "subtitleMode" not in serialized["downloadSettings"]


def test_subtitle_mp4_embedding_uses_mov_text_and_three_letter_language(tmp_path, monkeypatch):
    from dailywire_downloader import ffmpeg as ffmpeg_module

    media = tmp_path / "Movie.mp4"
    srt = tmp_path / "Movie.en.srt"
    media.write_bytes(b"media")
    srt.write_text("1\n00:00:00,100 --> 00:00:01,000\nHello\n")
    commands = []

    monkeypatch.setattr(ffmpeg_module.shutil, "which", lambda _: "/usr/bin/ffmpeg")

    def run(command, **_kwargs):
        commands.append(command)
        with open(command[-1], "wb") as out:
            out.write(b"embedded")
        return SimpleNamespace(returncode=0, stdout="")

    monkeypatch.setattr(ffmpeg_module.subprocess, "run", run)
    ffmpeg_module.embed_media(str(media), subtitles=(("en", str(srt), False),))

    assert media.read_bytes() == b"embedded"
    assert "-c:s" in commands[0]
    assert commands[0][commands[0].index("-c:s") + 1] == "mov_text"
    assert "language=eng" in commands[0]
    assert "1:s:0" in commands[0]


@pytest.mark.parametrize("publish,embed", [
    (True, False),
    (False, True),
    (True, True),
])
def test_subtitles_use_existing_publication_and_embedding_lifecycle(
    tmp_path, monkeypatch, publish, embed,
):
    from pathlib import Path

    from dailywire_downloader import coordinator, sidecars
    from dailywire_downloader.capacity import DownloadResources
    from dailywire_downloader.lifecycle import DownloadTracker
    from dailywire_downloader.models import DownloadProgress, DownloadResult

    payload = b"1\n00:00:01,000 --> 00:00:02,000\nHello\n\n"
    monkeypatch.setattr(sidecars, "download_hls_webvtt", lambda *_args, **_kwargs: payload)
    embedding_calls = []
    monkeypatch.setattr(
        coordinator, "embed_media",
        lambda *args, **kwargs: embedding_calls.append(kwargs),
    )

    def transfer(_url, destination, *, progress, should_cancel):
        Path(destination).write_bytes(b"media")
        progress(DownloadProgress(5, 5))
        return DownloadResult(destination, 5)

    monkeypatch.setattr(coordinator, "download_file", transfer)
    asset = SidecarSpec(
        "subtitle_0", "subtitle", url="https://cdn.example/subs.m3u8",
        source_format="hls_webvtt", extension="srt", language="en",
        target_suffix=".en.srt", publish=publish, required=False,
    )
    with DownloadTracker() as tracker:
        plan = build_download_plan(
            source=ResolvedDownloadSource(
                "https://cdn.example/Movie.mp4", "1080p", False, False, "mp4", False,
            ),
            requested_destination=tmp_path / "library" / "Movie.mp4",
            temporary_root=tmp_path / "temp", download_mode="temporary",
            assets=(asset,),
            subtitle_asset_ids=("subtitle_0",) if embed else (),
            attempt_id=tracker.attempt_id,
        )
        execution = coordinator.execute_download_plan(
            plan, tracker=tracker, resources=DownloadResources(),
        )
        assert Path(execution.result.path).read_bytes() == b"media"
        if publish:
            assert (tmp_path / "library" / "Movie.en.srt").read_bytes() == payload
            assert execution.assets[0].kind == "subtitle"
        else:
            assert not (tmp_path / "library" / "Movie.en.srt").exists()
            assert not execution.assets
        if embed:
            assert len(embedding_calls) == 1
            assert embedding_calls[0]["subtitles"] == (
                ("en", embedding_calls[0]["subtitles"][0][1], False),
            )
            assert Path(embedding_calls[0]["subtitles"][0][1]).is_file()
        else:
            assert embedding_calls == []
        execution.cleanup_workspace()


def test_unavailable_optional_subtitles_do_not_fail_media_download(tmp_path, monkeypatch):
    from pathlib import Path

    from dailywire_downloader import coordinator, sidecars
    from dailywire_downloader.capacity import DownloadResources
    from dailywire_downloader.errors import DownloadError
    from dailywire_downloader.lifecycle import DownloadTracker
    from dailywire_downloader.models import DownloadProgress, DownloadResult

    def missing(*_args, **_kwargs):
        raise DownloadError("Subtitle stream unavailable")

    monkeypatch.setattr(sidecars, "download_hls_webvtt", missing)

    def transfer(_url, path, *, progress, should_cancel):
        Path(path).write_bytes(b"media")
        progress(DownloadProgress(5, 5))
        return DownloadResult(path, 5)

    monkeypatch.setattr(coordinator, "download_file", transfer)
    asset = SidecarSpec(
        "subtitle_0", "subtitle", url="https://cdn.example/subs.m3u8",
        source_format="hls_webvtt", extension="srt", language="en",
        target_suffix=".en.srt", attempts=1, required=False,
    )
    with DownloadTracker() as tracker:
        plan = build_download_plan(
            source=ResolvedDownloadSource(
                "https://cdn.example/Movie.mp4", "1080p", False, False, "mp4", False,
            ),
            requested_destination=tmp_path / "library" / "Movie.mp4",
            temporary_root=tmp_path / "temp", download_mode="temporary",
            assets=(asset,), attempt_id=tracker.attempt_id,
        )
        execution = coordinator.execute_download_plan(
            plan, tracker=tracker, resources=DownloadResources(),
        )
        assert Path(execution.result.path).read_bytes() == b"media"
        assert execution.assets == ()
        assert not (tmp_path / "library" / "Movie.en.srt").exists()
        execution.cleanup_workspace()
