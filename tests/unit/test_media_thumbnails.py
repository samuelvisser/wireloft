from __future__ import annotations

from types import SimpleNamespace


def test_effective_thumbnail_mode_inherits_system_setting(monkeypatch):
    from config import get_settings
    from config.settings.submodels import ThumbnailMode
    from task_manager.tasks.helpers.downloads.download_modes import effective_thumbnail_mode

    settings = get_settings().download_settings
    monkeypatch.setattr(settings, "thumbnail_mode", ThumbnailMode.SIDECAR)

    profile = SimpleNamespace(thumbnail_mode="system")
    assert effective_thumbnail_mode(profile) is ThumbnailMode.SIDECAR


def test_effective_thumbnail_mode_honors_profile_override(monkeypatch):
    from config import get_settings
    from config.settings.submodels import ThumbnailMode
    from task_manager.tasks.helpers.downloads.download_modes import effective_thumbnail_mode

    settings = get_settings().download_settings
    monkeypatch.setattr(settings, "thumbnail_mode", ThumbnailMode.EMBED)

    profile = SimpleNamespace(thumbnail_mode="no_thumbnail")
    assert effective_thumbnail_mode(profile) is ThumbnailMode.NO_THUMBNAIL


def test_select_thumbnail_url_prefers_square_artwork():
    from task_manager.tasks.helpers.downloads.thumbnails import select_thumbnail_url

    media = SimpleNamespace(
        thumbnail_square_path="https://example.test/square.jpg",
        thumbnail_portrait_path="https://example.test/portrait.jpg",
        thumbnail_landscape_path="https://example.test/landscape.jpg",
        background_image_path="https://example.test/background.jpg",
    )

    assert select_thumbnail_url(media) == "https://example.test/square.jpg"


def test_select_thumbnail_url_ignores_non_http_paths():
    from task_manager.tasks.helpers.downloads.thumbnails import select_thumbnail_url

    media = SimpleNamespace(
        thumbnail_square_path="/local/square.jpg",
        thumbnail_portrait_path=None,
        thumbnail_landscape_path="https://example.test/landscape.jpg",
        background_image_path=None,
    )

    assert select_thumbnail_url(media) == "https://example.test/landscape.jpg"


def test_embed_thumbnail_uses_attached_picture_stream_for_audio(tmp_path, monkeypatch):
    from dailywire_downloader import ffmpeg as ffmpeg_module

    media = tmp_path / "episode.m4a"
    thumbnail = tmp_path / "thumbnail.jpg"
    media.write_bytes(b"media")
    thumbnail.write_bytes(b"image")
    commands: list[list[str]] = []

    monkeypatch.setattr(ffmpeg_module.shutil, "which", lambda _: "/usr/bin/ffmpeg")

    class Completed:
        returncode = 0
        stdout = ""

    def fake_run(command, **_kwargs):
        commands.append(command)
        with open(command[-1], "wb") as handle:
            handle.write(b"embedded")
        return Completed()

    monkeypatch.setattr(ffmpeg_module.subprocess, "run", fake_run)

    ffmpeg_module.embed_thumbnail(
        str(media),
        str(thumbnail),
        audio_only=True,
    )

    assert media.read_bytes() == b"embedded"
    command = commands[0]
    assert "-map" in command
    assert "1:v:0" in command
    assert "-disposition:v:0" in command
    assert "attached_pic" in command
    assert not any(argument.startswith("-frames:v:") for argument in command)
    assert command[command.index("-f") + 1] == "mp4"


def test_embed_thumbnail_refuses_to_replace_media_with_truncated_output(tmp_path, monkeypatch):
    import pytest

    from dailywire_downloader import ffmpeg as ffmpeg_module

    media = tmp_path / "episode.mp4"
    thumbnail = tmp_path / "thumbnail.jpg"
    original = b"media" * 100
    media.write_bytes(original)
    thumbnail.write_bytes(b"image")

    monkeypatch.setattr(ffmpeg_module.shutil, "which", lambda _: "/usr/bin/ffmpeg")

    class Completed:
        returncode = 0
        stdout = ""

    def fake_run(command, **_kwargs):
        with open(command[-1], "wb") as handle:
            handle.write(b"truncated")
        return Completed()

    monkeypatch.setattr(ffmpeg_module.subprocess, "run", fake_run)

    with pytest.raises(ffmpeg_module.DownloadError, match="unexpectedly small"):
        ffmpeg_module.embed_thumbnail(
            str(media),
            str(thumbnail),
            audio_only=False,
        )

    assert media.read_bytes() == original
    assert not (tmp_path / "episode.mp4.thumbnail.part").exists()


def test_sidecar_uses_media_basename_and_does_not_overwrite(tmp_path):
    import pytest

    from task_manager.tasks.helpers.downloads.engine import _publish_sidecar

    thumbnail = tmp_path / "source.jpg"
    thumbnail.write_bytes(b"image")
    media = tmp_path / "episode-2.mp4"
    media.write_bytes(b"media")

    result = _publish_sidecar(thumbnail, media)
    sidecar = tmp_path / "episode-2.jpg"
    assert result == str(sidecar)
    assert sidecar.read_bytes() == b"image"

    with pytest.raises(FileExistsError):
        _publish_sidecar(thumbnail, media)
    assert sidecar.read_bytes() == b"image"


def test_sidecar_refuses_external_empty_file_without_deleting_it(tmp_path):
    import pytest

    from task_manager.tasks.helpers.downloads.engine import _publish_sidecar

    thumbnail = tmp_path / "source.jpg"
    thumbnail.write_bytes(b"image")
    media = tmp_path / "episode.mp4"
    media.write_bytes(b"media")
    sidecar = tmp_path / "episode.jpg"
    sidecar.touch()

    with pytest.raises(FileExistsError):
        _publish_sidecar(thumbnail, media)

    assert sidecar.exists()
    assert sidecar.stat().st_size == 0


def test_remove_download_artifacts_removes_tracked_sidecar(tmp_path):
    from task_manager.tasks.helpers.downloads.download_files import remove_download_artifacts

    media = tmp_path / "episode.mp4"
    sidecar = tmp_path / "episode.jpg"
    media.write_bytes(b"media")
    sidecar.write_bytes(b"image")

    remove_download_artifacts(str(media), str(sidecar))

    assert not media.exists()
    assert not sidecar.exists()
