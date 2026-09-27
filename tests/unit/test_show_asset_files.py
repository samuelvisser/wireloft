from __future__ import annotations

import base64
from pathlib import Path
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
        self.headers = {"Content-Type": content_type, "Content-Length": str(len(content) if length is None else length)}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def raise_for_status(self):
        pass

    def iter_content(self, _size):
        yield self.content


def test_non_images_and_oversize_responses_are_rejected(tmp_path, monkeypatch):
    for response in (_Response(b"html", content_type="text/html"), _Response(b"image", length=files.MAX_ASSET_BYTES + 1)):
        monkeypatch.setattr(files.requests, "get", lambda *_args, **_kwargs: response)
        with pytest.raises(ValueError):
            files.download_show_asset_jpeg("https://example.invalid/art", tmp_path, ffmpeg_path="ffmpeg", check_cancelled=_active)
    assert not (tmp_path / "asset.jpg").exists()


def test_real_png_is_converted_to_jpeg_not_just_renamed(tmp_path, monkeypatch):
    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg is not installed")
    image = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAIAAAACCAIAAAD91JpzAAAAFklEQVR4nGP8z8DAwMDAxMDAwMDAAAANHQEDasKb6QAAAABJRU5ErkJggg==")
    monkeypatch.setattr(files.requests, "get", lambda *_args, **_kwargs: _Response(image))
    result = files.download_show_asset_jpeg("https://example.invalid/art", tmp_path, ffmpeg_path="ffmpeg", check_cancelled=_active)
    assert result.read_bytes().startswith(b"\xff\xd8\xff")


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
