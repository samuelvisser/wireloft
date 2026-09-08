from __future__ import annotations

from types import SimpleNamespace


def test_missing_artifact_without_identity_recovers_when_file_reappears(tmp_path):
    from backend.types.download_profile_types import MediaDownloadArtifactStatus
    from backend.utils.artifact_identity import inspect_artifact
    from task_manager.tasks.workers.file_watcher.service import _reconcile

    artifact = tmp_path / "reappeared.m4a"
    artifact.write_bytes(b"media that was unavailable during migration")
    download = SimpleNamespace(
        id=1,
        file_path=str(artifact),
        artifact_status=MediaDownloadArtifactStatus.MISSING.value,
        artifact_error="File not found",
        downloaded_bytes=artifact.stat().st_size,
        artifact_stat_dev=None,
        artifact_stat_ino=None,
        artifact_size_bytes=None,
        artifact_fingerprint=None,
    )

    assert _reconcile(download, verify_file_size=True) is True

    expected = inspect_artifact(artifact)
    assert download.artifact_status == MediaDownloadArtifactStatus.AVAILABLE.value
    assert download.artifact_error is None
    assert download.artifact_stat_dev == expected.stat_dev
    assert download.artifact_stat_ino == expected.stat_ino
    assert download.artifact_size_bytes == expected.size_bytes
    assert download.artifact_fingerprint == expected.fingerprint
