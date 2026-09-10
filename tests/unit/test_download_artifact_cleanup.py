from __future__ import annotations


def test_remove_download_artifacts_ignores_unresolved_template_path(tmp_path):
    from backend.utils.download_files import remove_download_artifacts

    unresolved = tmp_path / "Episode.ext"
    unresolved_part = tmp_path / "Episode.ext.part"
    unresolved.write_bytes(b"external file")
    unresolved_part.write_bytes(b"external part file")

    remove_download_artifacts(str(unresolved))

    assert unresolved.read_bytes() == b"external file"
    assert unresolved_part.read_bytes() == b"external part file"
