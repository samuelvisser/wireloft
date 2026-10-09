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
    from dailywire_downloader.storage.publication import PublicationJournal
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

    def publish(*args, **kwargs):
        assert old.read_bytes() == b"existing complete media"
        raise RuntimeError("sidecar publication failed")

    monkeypatch.setattr(coordinator, "download_file", download)
    monkeypatch.setattr(coordinator, "embed_media", embed)
    if fail_at == "sidecar":
        monkeypatch.setattr(PublicationJournal, "publish", publish)

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


def test_failed_filename_restoration_keeps_committed_replacement(
    old_download, monkeypatch,
):
    from backend.db.models.media_download import MediaDownloadBase
    from dailywire_downloader import coordinator
    from dailywire_downloader.storage import replacement
    from task_manager.tasks import download_adapter

    factory, media_download_id, old, sidecar, _ = old_download

    def download(_url, path, **kwargs):
        Path(path).write_bytes(b"new raw media")
        return DownloadResult(path, len(b"new raw media"))

    monkeypatch.setattr(coordinator, "download_file", download)
    monkeypatch.setattr(coordinator, "embed_media", lambda path, **kwargs: None)
    monkeypatch.setattr(replacement, "_stage_sibling", lambda *_: (_ for _ in ()).throw(OSError("link denied")))

    with factory() as session:
        download_adapter.run_download(
            session, media_download_id=media_download_id,
            is_redownload=True, prepare_existing_artifact=True,
        )

    assert old.exists() is False
    assert sidecar.exists() is False
    with factory() as session:
        current = session.get(MediaDownloadBase, media_download_id)
        assert current.file_path == str(old.with_name("Episode-1.mp4"))
        assert Path(current.file_path).read_bytes() == b"new raw media"
        assert Path(current.assets[0].path).read_bytes() == b"<new />"


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

    with factory() as session:
        download_adapter.run_download(
            session, media_download_id=media_download_id,
            is_redownload=True, prepare_existing_artifact=True,
        )

    assert old.read_bytes() == b"externally modified file"
    assert sidecar.read_bytes() == b"<old />"
    with factory() as session:
        download = session.get(MediaDownloadBase, media_download_id)
        assert download.file_path != str(old)
        assert Path(download.file_path).read_bytes() == b"new raw media"
        assert download.artifact_fingerprint == inspect_artifact(download.file_path).fingerprint


def test_startup_cleans_only_recognized_abandoned_replacement_staging(tmp_path):
    from dailywire_downloader.storage.temporary import cleanup_abandoned_publication_locks

    eligible = tmp_path / (".wireloft-replace-" + "a" * 32 + ".part")
    unrelated = tmp_path / ".wireloft-replace-user-file.part"
    eligible.write_bytes(b"abandoned staging")
    unrelated.write_bytes(b"not owned by WireLoft")

    assert cleanup_abandoned_publication_locks(tmp_path) == 1
    assert not eligible.exists()
    assert unrelated.read_bytes() == b"not owned by WireLoft"
