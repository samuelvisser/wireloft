from __future__ import annotations

import base64
import shutil

import pytest

from backend.utils import show_asset_files as files


def _active():
    pass


def test_atomic_publication_and_replacement(tmp_path):
    source = tmp_path / "source.jpg"
    source.write_bytes(b"first image")
    target = tmp_path / "show" / "poster.jpg"
    files.publish_show_asset(source, target, download_root=tmp_path, expected_hash=None, check_cancelled=_active)
    original = files.asset_file_hash(target)
    source.write_bytes(b"second image")
    files.publish_show_asset(source, target, download_root=tmp_path, expected_hash=original, check_cancelled=_active)
    assert target.read_bytes() == b"second image"
    assert not list(target.parent.glob(".wireloft-artwork-*"))


def test_custom_artwork_and_external_edits_are_preserved(tmp_path):
    source = tmp_path / "source.jpg"
    source.write_bytes(b"new image")
    target = tmp_path / "poster.jpg"
    target.write_bytes(b"custom image")
    with pytest.raises(files.ArtworkConflict):
        files.publish_show_asset(source, target, download_root=tmp_path, expected_hash=None, check_cancelled=_active)
    assert target.read_bytes() == b"custom image"
    assert not list(tmp_path.glob(".wireloft-artwork-*"))


def test_external_creation_during_atomic_claim_is_not_overwritten(tmp_path, monkeypatch):
    source = tmp_path / "source.jpg"
    source.write_bytes(b"new image")
    target = tmp_path / "poster.jpg"
    link = files.os.link

    def competing_writer(source, destination):
        target.write_bytes(b"custom image")
        return link(source, destination)

    monkeypatch.setattr(files.os, "link", competing_writer)
    with pytest.raises(files.ArtworkConflict):
        files.publish_show_asset(source, target, download_root=tmp_path, expected_hash=None, check_cancelled=_active)
    assert target.read_bytes() == b"custom image"


def test_failed_replacement_keeps_existing_image_and_cleans_temporary(tmp_path, monkeypatch):
    source = tmp_path / "source.jpg"
    source.write_bytes(b"new image")
    target = tmp_path / "poster.jpg"
    target.write_bytes(b"old image")
    expected = files.asset_file_hash(target)

    def fail_replace(*_args):
        raise OSError("unavailable filesystem")

    monkeypatch.setattr(files.os, "replace", fail_replace)
    with pytest.raises(OSError):
        files.publish_show_asset(source, target, download_root=tmp_path, expected_hash=expected, check_cancelled=_active)
    assert target.read_bytes() == b"old image"
    assert not list(tmp_path.glob(".wireloft-artwork-*"))


def test_outside_paths_symlinks_and_directories_are_rejected(tmp_path):
    with pytest.raises(files.ArtworkConflict):
        files.safe_asset_path(tmp_path, tmp_path.parent / "poster.jpg")
    target = tmp_path / "poster.jpg"
    target.mkdir()
    with pytest.raises(files.ArtworkConflict):
        files.asset_file_hash(target)
    target.rmdir()
    try:
        target.symlink_to(tmp_path / "not-yet-created")
    except OSError:
        pytest.skip("Symlinks unavailable")
    with pytest.raises(files.ArtworkConflict):
        files.safe_asset_path(tmp_path, target)


class _Response:
    def __init__(self, content, *, content_type="image/png", length=None):
        self.content = content
        self.headers = {
            "Content-Type": content_type,
            "Content-Length": str(len(content) if length is None else length),
        }

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self):
        pass

    def iter_content(self, _size):
        yield self.content


def test_non_images_and_oversize_responses_are_rejected(tmp_path, monkeypatch):
    for response in (
        _Response(b"html", content_type="text/html"),
        _Response(b"image", length=files.MAX_ASSET_BYTES + 1),
    ):
        monkeypatch.setattr(files.requests, "get", lambda *_args, **_kwargs: response)
        with pytest.raises(ValueError):
            files.download_show_asset(
                "https://example.invalid/art",
                tmp_path,
                ffmpeg_path="ffmpeg",
                fallback_format="jpg",
                check_cancelled=_active,
            )
    assert not list(tmp_path.glob("asset.*"))


def test_native_png_stays_png(tmp_path, monkeypatch):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg is not installed")
    image = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAYAAABytg0kAAAACXBIWXMAAAAAAAAAAQCEeRdzAAAAEUlEQVR4nGP4z8BgD8IMMAYAMUoE+QYxJhsAAAAASUVORK5CYII="
    )
    monkeypatch.setattr(files.requests, "get", lambda *_args, **_kwargs: _Response(image))
    result = files.download_show_asset(
        "https://example.invalid/art",
        tmp_path,
        ffmpeg_path="ffmpeg",
        fallback_format="jpg",
        check_cancelled=_active,
    )
    assert result.source_format == "png"
    assert result.output_format == "png"
    assert result.path.suffix == ".png"
    data = result.path.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert data[25] == 6


def test_non_native_image_uses_configured_fallback(tmp_path, monkeypatch):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg is not installed")
    webp = base64.b64decode("UklGRhwAAABXRUJQVlA4TA8AAAAvAUAAEAcQ/Y/+BCKi/wEA")
    monkeypatch.setattr(
        files.requests,
        "get",
        lambda *_args, **_kwargs: _Response(webp, content_type="image/webp"),
    )
    jpg = files.download_show_asset(
        "https://example.invalid/art",
        tmp_path / "jpg",
        ffmpeg_path="ffmpeg",
        fallback_format="jpg",
        check_cancelled=_active,
    )
    assert jpg.source_format == "other"
    assert jpg.output_format == "jpg"
    assert jpg.path.read_bytes().startswith(b"\xff\xd8\xff")

    png = files.download_show_asset(
        "https://example.invalid/art",
        tmp_path / "png",
        ffmpeg_path="ffmpeg",
        fallback_format="png",
        check_cancelled=_active,
    )
    assert png.source_format == "other"
    assert png.output_format == "png"
    assert png.path.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_forced_png_overrides_fallback_for_clearlogos(tmp_path, monkeypatch):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg is not installed")
    webp = base64.b64decode(
        "UklGRjwAAABXRUJQVlA4IDAAAADQAQCdASoCAAIAAgA0JaACdLoB+AADsAD+8MQL/yC5YXXI1/8gP+QH/ID/+PIAAAA="
    )
    monkeypatch.setattr(
        files.requests,
        "get",
        lambda *_args, **_kwargs: _Response(webp, content_type="image/webp"),
    )
    result = files.download_show_asset(
        "https://example.invalid/logo",
        tmp_path,
        ffmpeg_path="ffmpeg",
        fallback_format="jpg",
        forced_format="png",
        check_cancelled=_active,
    )
    assert result.source_format == "other"
    assert result.output_format == "png"
    data = result.path.read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert data[25] == 6


def test_cancellation_before_publication_leaves_no_target(tmp_path):
    source = tmp_path / "source.jpg"
    source.write_bytes(b"image")
    target = tmp_path / "show" / "poster.jpg"

    def canceled():
        raise RuntimeError("canceled")

    with pytest.raises(RuntimeError, match="canceled"):
        files.publish_show_asset(source, target, download_root=tmp_path, expected_hash=None, check_cancelled=canceled)
    assert not target.exists()
    assert not list(target.parent.glob(".wireloft-artwork-*"))
