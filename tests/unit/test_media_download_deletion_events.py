from __future__ import annotations

from types import SimpleNamespace


class _FakeSession:
    def __init__(self):
        self.added = []

    def add(self, value):
        self.added.append(value)


def _download(*, artifact_status: str):
    return SimpleNamespace(
        id=42,
        artifact_status=artifact_status,
        artifact_error=None,
        artifact_stat_dev="1",
        artifact_stat_ino="2",
        artifact_size_bytes=100,
        artifact_fingerprint="fingerprint",
        automatic_retry_suppressed=False,
        downloaded_bytes=100,
        format_downloaded="format_audio_only",
        downloaded_at=object(),
        thumbnail_path=None,
        file_path="/downloads/episode.m4a",
    )


def test_preparing_existing_artifact_records_deletion_event(monkeypatch):
    from task_manager.tasks import media_download_operations

    session = _FakeSession()
    download = _download(artifact_status="available")
    removed = []

    monkeypatch.setattr(
        media_download_operations,
        "resolve_media_download_file",
        lambda _session, _download: "/downloads/episode.m4a",
    )
    monkeypatch.setattr(
        media_download_operations,
        "remove_download_artifacts",
        lambda file_path, thumbnail_path=None: removed.append((file_path, thumbnail_path)),
    )

    media_download_operations.prepare_media_download_artifact(session, download)

    assert len(session.added) == 1
    event = session.added[0]
    assert event.media_download_id == 42
    assert event.event_type == "deleted"
    assert event.file_path == "/downloads/episode.m4a"
    assert removed == [("/downloads/episode.m4a", None)]
    assert download.artifact_status == "absent"


def test_preparing_missing_artifact_does_not_claim_wireloft_deleted_it(monkeypatch):
    from task_manager.tasks import media_download_operations

    session = _FakeSession()
    download = _download(artifact_status="missing")

    monkeypatch.setattr(
        media_download_operations,
        "resolve_media_download_file",
        lambda _session, _download: None,
    )
    monkeypatch.setattr(media_download_operations, "remove_download_artifacts", lambda *_args: None)

    media_download_operations.prepare_media_download_artifact(session, download)

    assert session.added == []
    assert download.artifact_status == "absent"
