from __future__ import annotations


def test_remove_download_artifacts_ignores_unresolved_template_path(tmp_path):
    from dailywire_downloader.storage.artifacts import remove_download_artifacts

    unresolved = tmp_path / "Episode.ext"
    unresolved_part = tmp_path / "Episode.ext.part"
    unresolved.write_bytes(b"external file")
    unresolved_part.write_bytes(b"external part file")

    remove_download_artifacts(str(unresolved))

    assert unresolved.read_bytes() == b"external file"
    assert unresolved_part.read_bytes() == b"external part file"


def test_remove_download_artifacts_strict_mode_propagates_filesystem_errors(tmp_path, monkeypatch):
    from pathlib import Path

    import pytest

    from dailywire_downloader.storage.artifacts import remove_download_artifacts

    media = tmp_path / "episode.m4a"
    media.write_bytes(b"media")
    original_unlink = Path.unlink

    def reject_media_unlink(path, *args, **kwargs):
        if path == media:
            raise PermissionError("Cannot remove media")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", reject_media_unlink)

    with pytest.raises(PermissionError, match="Cannot remove media"):
        remove_download_artifacts(str(media), raise_on_error=True)

    assert media.exists()
