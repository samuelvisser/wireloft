"""Re-downloads keep the previously committed media usable until replacement."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from dailywire_downloader.models import DownloadResult
from dailywire_downloader.plan import ResolvedDownloadSource, SidecarSpec, build_download_plan
from dailywire_downloader.storage.identity import inspect_artifact


@pytest.fixture
def old_download(task_database, tmp_path, monkeypatch):
    from backend.db import Base
    from backend.db.models.media_download import MediaDownloadAsset
    from task_manager.tasks import download_adapter
    from test_media_download_operations import _make_download

    old = tmp_path / "library" / "Episode.mp4"
    old.parent.mkdir(parents=True)
    old.write_bytes(b"existing complete media")
    sidecar = old.with_suffix(".nfo")
    sidecar.write_bytes(b"<old />")
    old_identity = inspect_artifact(old)
    asset_identity = inspect_artifact(sidecar)
    downloaded_at = datetime(2026, 1, 2, tzinfo=timezone.utc)

    with task_database() as session:
        Base.metadata.create_all(session.bind)
        download = _make_download(session, slug="replacement")
        download.file_path = str(old)
        download.artifact_status = "available"
        download.downloaded_at = downloaded_at
        download.downloaded_bytes = old_identity.size_bytes
        download.format_downloaded = "old"
        download.artifact_stat_dev = old_identity.stat_dev
        download.artifact_stat_ino = old_identity.stat_ino
        download.artifact_size_bytes = old_identity.size_bytes
        download.artifact_fingerprint = old_identity.fingerprint
        download.assets.append(MediaDownloadAsset(
            asset_key="nfo", kind="nfo", path=str(sidecar), suffix=".nfo",
            size_bytes=asset_identity.size_bytes, fingerprint=asset_identity.fingerprint,
        ))
        session.commit()
        media_download_id = download.id

    def prepare(session, _media_download_id, tracker, *, destination=None, mode="temporary"):
        session.rollback()
        return build_download_plan(
            source=ResolvedDownloadSource(
                "https://media.test/file.mp4", "1080p", False, False, "mp4", False,
            ),
            requested_destination=destination or old,
            temporary_root=tmp_path / "temporary",
            download_mode=mode,
            assets=(SidecarSpec("nfo", "nfo", content=b"<new />", extension="nfo"),),
            metadata_tags=(("title", "new"),),
            attempt_id=tracker.attempt_id,
        )

    monkeypatch.setattr(
        download_adapter, "on_media_download_transfer_complete", lambda: None,
    )
    monkeypatch.setattr(download_adapter, "prepare_download_plan", prepare)
    return task_database, media_download_id, old, sidecar, downloaded_at


@pytest.mark.parametrize("mode", ["direct", "temporary"])
def test_redownload_preserves_old_media_until_processed_and_replaces_in_place(
    old_download, monkeypatch, mode,
):
    from backend.db.models.media_download import MediaDownloadBase
    from dailywire_downloader import coordinator
    from task_manager.tasks import download_adapter

    factory, media_download_id, old, sidecar, downloaded_at = old_download
    original_prepare = download_adapter.prepare_download_plan

    def prepare(session, media_id, tracker):
        return original_prepare(session, media_id, tracker, mode=mode)

    monkeypatch.setattr(download_adapter, "prepare_download_plan", prepare)
    phases = []

    def download(_url, path, *, progress, should_cancel):
        phases.append("transfer")
        assert old.read_bytes() == b"existing complete media"
        assert sidecar.read_bytes() == b"<old />"
        with factory() as db:
            previous = db.get(MediaDownloadBase, media_download_id)
            assert previous.file_path == str(old)
            assert previous.artifact_status == "available"
            assert previous.downloaded_at == downloaded_at
        Path(path).write_bytes(b"new raw media")
        return DownloadResult(path, len(b"new raw media"))

    def embed(path, **kwargs):
        phases.append("postprocess")
        assert old.read_bytes() == b"existing complete media"
        assert sidecar.read_bytes() == b"<old />"
        Path(path).write_bytes(b"new fully processed media")

    monkeypatch.setattr(coordinator, "download_file", download)
    monkeypatch.setattr(coordinator, "embed_media", embed)

    with factory() as session:
        download_adapter.run_download(
            session, media_download_id=media_download_id,
            is_redownload=True, prepare_existing_artifact=True,
        )

    assert phases == ["transfer", "postprocess"]
    assert old.read_bytes() == b"new fully processed media"
    assert sidecar.read_bytes() == b"<new />"
    assert not (old.parent / "Episode-1.mp4").exists()
    assert not (old.parent / "Episode-1.nfo").exists()
    with factory() as session:
        current = session.get(MediaDownloadBase, media_download_id)
        assert current.file_path == str(old)
        assert current.artifact_status == "available"
        assert current.downloaded_at > downloaded_at
        assert current.artifact_fingerprint == inspect_artifact(old).fingerprint
        assert current.assets[0].path == str(sidecar)
        assert current.assets[0].fingerprint == inspect_artifact(sidecar).fingerprint


@pytest.mark.parametrize("fail_at", ["transfer", "postprocess", "sidecar"])
def test_failed_redownload_keeps_old_media_and_database_facts(
    old_download, monkeypatch, fail_at,
):
    from backend.db.models.media_download import MediaDownloadBase
    from dailywire_downloader import coordinator
    from dailywire_downloader.storage import replacement
    from task_manager.tasks import download_adapter

    factory, media_download_id, old, sidecar, downloaded_at = old_download

    def download(_url, path, **kwargs):
        assert old.read_bytes() == b"existing complete media"
        if fail_at == "transfer":
            raise RuntimeError("transfer failed")
        Path(path).write_bytes(b"new raw media")
        return DownloadResult(path, len(b"new raw media"))

    def embed(path, **kwargs):
        assert old.read_bytes() == b"existing complete media"
        if fail_at == "postprocess":
            raise RuntimeError("post-processing failed")
        Path(path).write_bytes(b"new fully processed media")

    stage_file = replacement._stage_completed_file

    def stage(source, destination, **kwargs):
        if fail_at == "sidecar" and source.suffix == ".nfo":
            assert old.read_bytes() == b"existing complete media"
            raise RuntimeError("sidecar staging failed")
        return stage_file(source, destination, **kwargs)

    monkeypatch.setattr(coordinator, "download_file", download)
    monkeypatch.setattr(coordinator, "embed_media", embed)
    monkeypatch.setattr(replacement, "_stage_completed_file", stage)

    with factory() as session, pytest.raises(RuntimeError):
        download_adapter.run_download(
            session, media_download_id=media_download_id,
            is_redownload=True, prepare_existing_artifact=True,
        )

    assert old.read_bytes() == b"existing complete media"
    assert sidecar.read_bytes() == b"<old />"
    assert not (old.parent / "Episode-1.mp4").exists()
    with factory() as session:
        current = session.get(MediaDownloadBase, media_download_id)
        assert current.file_path == str(old)
        assert current.artifact_status == "available"
        assert current.downloaded_at == downloaded_at
        assert current.artifact_fingerprint == inspect_artifact(old).fingerprint
        assert current.assets[0].path == str(sidecar)


def test_changed_destination_swaps_database_first_then_retires_old(
    old_download, tmp_path, monkeypatch,
):
    from backend.db.models.media_download import MediaDownloadBase
    from dailywire_downloader import coordinator
    from task_manager.tasks import download_adapter

    factory, media_download_id, old, sidecar, _ = old_download
    requested = tmp_path / "library" / "Renamed.mp4"
    original_prepare = download_adapter.prepare_download_plan

    def prepare(session, media_id, tracker):
        return original_prepare(session, media_id, tracker, destination=requested)

    def download(_url, path, **kwargs):
        assert old.read_bytes() == b"existing complete media"
        Path(path).write_bytes(b"new raw media")
        return DownloadResult(path, len(b"new raw media"))

    monkeypatch.setattr(download_adapter, "prepare_download_plan", prepare)
    monkeypatch.setattr(coordinator, "download_file", download)
    monkeypatch.setattr(coordinator, "embed_media", lambda path, **kwargs: None)

    with factory() as session:
        download_adapter.run_download(
            session, media_download_id=media_download_id,
            is_redownload=True, prepare_existing_artifact=True,
        )

    assert requested.read_bytes() == b"new raw media"
    assert not old.exists()
    assert not sidecar.exists()
    with factory() as session:
        current = session.get(MediaDownloadBase, media_download_id)
        assert current.file_path == str(requested)
        assert current.artifact_fingerprint == inspect_artifact(requested).fingerprint


def test_replacement_failure_before_staging_preserves_original(
    old_download, monkeypatch,
):
    from backend.db.models.media_download import MediaDownloadBase
    from dailywire_downloader import coordinator
    from dailywire_downloader.storage import replacement
    from task_manager.tasks import download_adapter

    factory, media_download_id, old, sidecar, downloaded_at = old_download

    def download(_url, path, **kwargs):
        Path(path).write_bytes(b"new raw media")
        return DownloadResult(path, len(b"new raw media"))

    monkeypatch.setattr(coordinator, "download_file", download)
    monkeypatch.setattr(coordinator, "embed_media", lambda path, **kwargs: None)
    monkeypatch.setattr(
        replacement, "_stage_completed_file",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("stage failed")),
    )
    with factory() as session, pytest.raises(OSError, match="stage failed"):
        download_adapter.run_download(
            session, media_download_id=media_download_id,
            is_redownload=True, prepare_existing_artifact=True,
        )

    assert old.read_bytes() == b"existing complete media"
    assert sidecar.read_bytes() == b"<old />"
    assert not list(old.parent.glob(".wireloft-replacement-*.json"))
    with factory() as session:
        current = session.get(MediaDownloadBase, media_download_id)
        assert current.file_path == str(old)
        assert current.downloaded_at == downloaded_at


def test_retiring_replaced_hls_removes_only_owned_bundle(tmp_path):
    from dailywire_downloader.storage.replacement import (
        OwnedFile, PreviousDownload, retire_superseded_files,
    )
    from dailywire_downloader.hls_bundle import hls_asset_marker

    master = tmp_path / "video.m3u8"
    master.write_text("#EXTM3U\n", encoding="utf-8")
    marker = hls_asset_marker(master)
    marker.parent.mkdir()
    marker.write_text("WireLoft local HLS bundle\n", encoding="utf-8")
    previous = PreviousDownload(OwnedFile(master, inspect_artifact(master)), ())
    retire_superseded_files(previous, retained_paths=frozenset())
    assert not master.exists()
    assert not marker.parent.exists()


def test_cancelled_redownload_keeps_the_previous_download(old_download, monkeypatch):
    from backend.db.models.media_download import MediaDownloadBase
    from dailywire_downloader import DownloadCancelled, coordinator
    from task_manager.tasks import download_adapter

    factory, media_download_id, old, sidecar, downloaded_at = old_download

    def cancelled_download(_url, path, **kwargs):
        assert old.read_bytes() == b"existing complete media"
        Path(path).write_bytes(b"incomplete replacement")
        raise DownloadCancelled("User cancelled the attempt")

    monkeypatch.setattr(coordinator, "download_file", cancelled_download)
    with factory() as session, pytest.raises(DownloadCancelled):
        download_adapter.run_download(
            session, media_download_id=media_download_id,
            is_redownload=True, prepare_existing_artifact=True,
        )

    assert old.read_bytes() == b"existing complete media"
    assert sidecar.read_bytes() == b"<old />"
    with factory() as session:
        download = session.get(MediaDownloadBase, media_download_id)
        assert download.file_path == str(old)
        assert download.artifact_status == "available"
        assert download.downloaded_at == downloaded_at


def test_external_modification_during_redownload_is_not_overwritten(
    old_download, monkeypatch,
):
    from backend.db.models.media_download import MediaDownloadBase
    from dailywire_downloader import coordinator
    from task_manager.tasks import download_adapter

    factory, media_download_id, old, sidecar, _ = old_download

    def download(_url, path, **kwargs):
        # An external writer takes over the old path after its ownership was
        # captured. Replacement may complete, but cleanup cannot delete it.
        old.write_bytes(b"externally modified file")
        Path(path).write_bytes(b"new raw media")
        return DownloadResult(path, len(b"new raw media"))

    monkeypatch.setattr(coordinator, "download_file", download)
    monkeypatch.setattr(coordinator, "embed_media", lambda path, **kwargs: None)

    with factory() as session, pytest.raises(Exception, match="Existing replacement destination changed"):
        download_adapter.run_download(
            session, media_download_id=media_download_id,
            is_redownload=True, prepare_existing_artifact=True,
        )

    assert old.read_bytes() == b"externally modified file"
    assert sidecar.read_bytes() == b"<old />"
    with factory() as session:
        download = session.get(MediaDownloadBase, media_download_id)
        assert download.file_path == str(old)
        assert download.artifact_status == "available"
        assert download.artifact_fingerprint != inspect_artifact(download.file_path).fingerprint


def test_startup_cleans_only_recognized_abandoned_replacement_staging(tmp_path):
    from dailywire_downloader.storage.replacement import reconcile_abandoned_replacements

    eligible = tmp_path / (".wireloft-replace-" + "a" * 32 + ".part")
    unrelated = tmp_path / ".wireloft-replace-user-file.part"
    eligible.write_bytes(b"abandoned staging")
    unrelated.write_bytes(b"not owned by WireLoft")

    assert reconcile_abandoned_replacements(tmp_path, recover=lambda *_: True) == 0
    assert not eligible.exists()
    assert unrelated.read_bytes() == b"not owned by WireLoft"


def _publish_without_database_commit(
    old_download, tmp_path, *,
    monkeypatch=None, interrupt_at=None,
):
    """Exercise the real publication boundary without committing SQLAlchemy."""
    from backend.db.models.media_download import MediaDownloadBase
    from dailywire_downloader.storage import replacement

    factory, download_id, old, sidecar, _ = old_download
    media = tmp_path / "prepared.mp4"
    nfo = tmp_path / "prepared.nfo"
    media.write_bytes(b"verified replacement media")
    nfo.write_bytes(b"<new />")
    with factory() as session:
        download = session.get(MediaDownloadBase, download_id)
        previous = replacement.capture_previous_download(
            download.file_path,
            size_bytes=download.artifact_size_bytes,
            fingerprint=download.artifact_fingerprint,
            assets=tuple((a.path, a.size_bytes, a.fingerprint) for a in download.assets),
        )
    assert previous is not None

    if interrupt_at is not None:
        original_replace = replacement.os.replace

        def interrupt(source, destination):
            if Path(destination) == old and Path(source).name.startswith(".wireloft-replace-"):
                if interrupt_at == "before_media_rename":
                    raise OSError("simulated crash immediately before atomic rename")
                original_replace(source, destination)
                if interrupt_at == "after_media_rename":
                    raise OSError("simulated crash immediately after atomic rename")
                return
            return original_replace(source, destination)

        assert monkeypatch is not None
        monkeypatch.setattr(replacement.os, "replace", interrupt)

    kwargs = dict(
        media_download_id=download_id,
        previous=previous,
        media_source=media,
        sidecars=(replacement.ReplacementSidecar("nfo", "nfo", nfo, ".nfo"),),
        downloaded_bytes=123,
        format_downloaded="new format",
        downloaded_publish_status="published_final",
        should_cancel=lambda: False,
    )
    if interrupt_at is not None:
        with pytest.raises(OSError, match="simulated crash"):
            replacement.publish_replacement(**kwargs)
    else:
        replacement.publish_replacement(**kwargs)
    return old, sidecar


@pytest.mark.parametrize("interrupt_at", [None, "before_media_rename", "after_media_rename"])
def test_startup_recovery_finishes_atomic_replacement_and_database(
    old_download, tmp_path, monkeypatch, interrupt_at,
):
    from backend.db.models.media_download import MediaDownloadBase, MediaDownloadHistory
    from backend.services.download_recovery import recover_abandoned_download_replacements
    from dailywire_downloader.storage import replacement
    from sqlalchemy import select

    factory, media_download_id, old, sidecar, downloaded_at = old_download
    _publish_without_database_commit(
        old_download, tmp_path, monkeypatch=monkeypatch,
        interrupt_at=interrupt_at,
    )
    if interrupt_at is not None:
        # Simulate a new process, with the original OS rename function restored.
        monkeypatch.undo()

    with factory() as session:
        stale = session.get(MediaDownloadBase, media_download_id)
        assert stale.downloaded_at == downloaded_at
        if interrupt_at != "before_media_rename":
            assert stale.artifact_fingerprint != inspect_artifact(old).fingerprint

    assert recover_abandoned_download_replacements(old.parent) == 1
    assert old.read_bytes() == b"verified replacement media"
    assert sidecar.read_bytes() == b"<new />"
    assert not list(old.parent.glob(".wireloft-replacement-*.json"))
    assert not list(old.parent.glob(".wireloft-replace-*.part"))
    with factory() as session:
        refreshed = session.get(MediaDownloadBase, media_download_id)
        assert refreshed.file_path == str(old)
        assert refreshed.artifact_status == "available"
        assert refreshed.downloaded_at > downloaded_at
        assert refreshed.artifact_fingerprint == inspect_artifact(old).fingerprint
        assert refreshed.format_downloaded == "new format"
        assert refreshed.assets[0].path == str(sidecar)
        assert refreshed.assets[0].fingerprint == inspect_artifact(sidecar).fingerprint
        history = list(session.scalars(select(MediaDownloadHistory).where(
            MediaDownloadHistory.media_download_id == media_download_id,
            MediaDownloadHistory.action == "completed",
        )))
        assert len(history) == 1
        assert history[0].event_metadata["recovered_after_restart"] is True
    # Idempotent startup: a second run cannot record a duplicate completion.
    assert recover_abandoned_download_replacements(old.parent) == 0


def test_startup_recovery_preserves_newer_external_media(
    old_download, tmp_path, monkeypatch,
):
    from backend.db.models.media_download import MediaDownloadBase
    from backend.services.download_recovery import recover_abandoned_download_replacements

    factory, media_download_id, old, sidecar, _ = old_download
    _publish_without_database_commit(
        old_download, tmp_path, monkeypatch=monkeypatch,
        interrupt_at="before_media_rename",
    )
    monkeypatch.undo()
    old.write_bytes(b"externally modified media")

    assert recover_abandoned_download_replacements(old.parent) == 0
    assert old.read_bytes() == b"externally modified media"
    assert list(old.parent.glob(".wireloft-replacement-*.json"))
    with factory() as session:
        current = session.get(MediaDownloadBase, media_download_id)
        assert current.artifact_fingerprint != inspect_artifact(old).fingerprint


def test_recovery_preserves_corrupted_staging_for_investigation(
    old_download, tmp_path, monkeypatch,
):
    from backend.services.download_recovery import recover_abandoned_download_replacements
    from dailywire_downloader.storage import replacement

    _, _, old, _, _ = old_download
    _publish_without_database_commit(
        old_download, tmp_path, monkeypatch=monkeypatch,
        interrupt_at="before_media_rename",
    )
    monkeypatch.undo()
    journal = next(old.parent.glob(".wireloft-replacement-*.json"))
    record = replacement._load_record(journal, old.parent)
    assert record is not None
    Path(record["media"]["staged"]).write_bytes(b"invalid staging data")

    assert recover_abandoned_download_replacements(old.parent) == 0
    assert journal.exists()
    assert old.read_bytes() == b"existing complete media"


def test_recovery_after_database_commit_only_cleans_journal(
    old_download, tmp_path,
):
    from backend.db.models.media_download import MediaDownloadBase, MediaDownloadHistory
    from backend.services.download_recovery import (
        _commit_abandoned_replacement, recover_abandoned_download_replacements,
    )
    from dailywire_downloader.storage import replacement
    from sqlalchemy import select

    factory, media_download_id, old, sidecar, _ = old_download
    _publish_without_database_commit(old_download, tmp_path)
    journal = next(old.parent.glob(".wireloft-replacement-*.json"))
    record = replacement._load_record(journal, old.parent)
    assert record is not None

    # First recovery commits new identity, then the process crashes before
    # journal cleanup. The following startup must not add a second completion.
    assert _commit_abandoned_replacement(record, lambda: True)
    with factory() as session:
        completed_before = session.scalar(
            select(MediaDownloadHistory.id).where(
                MediaDownloadHistory.media_download_id == media_download_id,
                MediaDownloadHistory.action == "completed",
            )
        )
    assert recover_abandoned_download_replacements(old.parent) == 1
    with factory() as session:
        downloaded = session.get(MediaDownloadBase, media_download_id)
        assert downloaded.file_path == str(old)
        assert downloaded.artifact_fingerprint == inspect_artifact(old).fingerprint
        completed_after = session.scalar(
            select(MediaDownloadHistory.id).where(
                MediaDownloadHistory.media_download_id == media_download_id,
                MediaDownloadHistory.action == "completed",
            )
        )
        assert completed_before == completed_after
    assert not journal.exists()


def test_direct_mode_uses_existing_workspace_startup_cleanup(tmp_path):
    from dailywire_downloader.storage import create_temporary_download_workspace
    from dailywire_downloader.storage.temporary import cleanup_abandoned_destination_workspaces

    download_root = tmp_path / "downloads"
    destination = download_root / "show" / "episode.mp4"
    workspace = create_temporary_download_workspace(destination.parent, destination)
    part = workspace.path.with_name(workspace.path.name + ".part")
    part.write_bytes(b"interrupted direct-mode media")

    assert workspace.workspace.exists()
    assert cleanup_abandoned_destination_workspaces(
        download_root, is_committed=lambda *_: False,
    ) == 1
    assert not workspace.workspace.exists()
    assert not part.exists()


def test_stale_journal_cannot_replace_database_owner(
    old_download, tmp_path, monkeypatch,
):
    from backend.db.models.media_download import MediaDownloadBase
    from backend.services.download_recovery import recover_abandoned_download_replacements
    from dailywire_downloader.storage.identity import inspect_artifact

    factory, media_download_id, old, sidecar, _ = old_download
    _publish_without_database_commit(
        old_download, tmp_path, monkeypatch=monkeypatch,
        interrupt_at="before_media_rename",
    )
    monkeypatch.undo()
    with factory() as session:
        current = session.get(MediaDownloadBase, media_download_id)
        current.artifact_fingerprint = "e" * 64
        session.commit()

    assert recover_abandoned_download_replacements(old.parent) == 0
    assert old.read_bytes() == b"existing complete media"
    assert list(old.parent.glob(".wireloft-replacement-*.json"))
