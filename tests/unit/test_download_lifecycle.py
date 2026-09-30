from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
from threading import Event

import pytest

from dailywire_downloader.errors import DownloadCancelled
from dailywire_downloader.lifecycle import DownloadTracker
from dailywire_downloader.models import DownloadProgress, DownloadResult
from dailywire_downloader.plan import ResolvedDownloadSource, SidecarSpec, build_download_plan
from dailywire_downloader.capacity import DownloadResources


def plan(tmp_path, tracker, **options):
    return build_download_plan(
        source=ResolvedDownloadSource("https://media.test/media.mp4", "1080p", False, False, "mp4", False, expected_bytes=100),
        requested_destination=tmp_path / "library" / "Example.mp4",
        download_mode="temporary", temporary_root=tmp_path / "temp", attempt_id=tracker.attempt_id,
        **options,
    )


def test_plan_resolves_optional_stages_and_generated_assets(tmp_path):
    tracker = DownloadTracker()
    value = plan(tmp_path, tracker, assets=(SidecarSpec("artwork", "thumbnail", url="https://media.test/image.jpg", publish=False), SidecarSpec("nfo", "nfo", content=b"<movie/>", extension="nfo")), artwork_asset_id="artwork", metadata_tags=(("title", "Example"),))
    assert value.stage("embed").code == "embed_artwork_metadata"
    assert not any(stage.id == "publish:artwork" for stage in value.stages)
    assert value.stage("acquire:nfo").code == "generate_sidecar"
    assert not (tmp_path / "library").exists()
    with pytest.raises(Exception):
        value.download_mode = "direct"


def test_individual_progress_is_media_only_and_finishing_does_not_complete_attempt(tmp_path):
    snapshots = []
    tracker = DownloadTracker(snapshots.append, report_interval=0)
    value = plan(tmp_path, tracker, metadata_tags=(("title", "Example"),))
    tracker.install(value)
    tracker.start("media")
    tracker.progress("media", DownloadProgress(50, 100))
    tracker.complete("media")
    tracker.start("embed")
    snapshot = snapshots[-1]
    assert snapshot.phase == "finishing"
    assert snapshot.primary_transfer_complete
    assert snapshot.main_activity == "embed"
    assert next(stage for stage in snapshot.stages if stage.id == "media").fraction == 1
    assert next(stage for stage in snapshot.stages if stage.id == "embed").fraction is None


def test_sidecar_wait_does_not_replace_main_media_activity(tmp_path):
    tracker = DownloadTracker()
    tracker.install(plan(tmp_path, tracker, assets=(SidecarSpec("artwork", "thumbnail", url="https://media.test/a.jpg"),)))
    tracker.start("media")
    tracker.start("acquire:artwork", foreground=False)
    tracker.wait("acquire:artwork", "upstream_retry", 123)
    assert tracker.snapshot().main_activity == "media"
    assert next(stage for stage in tracker.snapshot().stages if stage.id == "media").wait is None


def test_coordinator_overlaps_artwork_then_embeds_once_and_publishes_nfo(tmp_path, monkeypatch):
    from dailywire_downloader import coordinator, sidecars
    artwork_started, media_started = Event(), Event()
    class Response:
        headers = {"Content-Type": "image/jpeg", "Content-Length": "5"}
        def __enter__(self):
            artwork_started.set()
            assert media_started.wait(2)
            return self
        def __exit__(self, *_args): pass
        def iter_chunks(self, _size): yield b"image"
    monkeypatch.setattr(sidecars, "http_get", lambda *_args, **_kwargs: Response())
    def download(_url, destination, *, progress, should_cancel):
        media_started.set()
        assert artwork_started.wait(2)
        Path(destination).write_bytes(b"m" * 100)
        progress(DownloadProgress(100, 100))
        return DownloadResult(destination, 100)
    monkeypatch.setattr(coordinator, "download_file", download)
    calls = []
    monkeypatch.setattr(coordinator, "embed_media", lambda *args, **kwargs: calls.append((args, kwargs)))
    states = []
    with DownloadTracker(states.append, report_interval=0) as tracker:
        value = plan(tmp_path, tracker, assets=(SidecarSpec("artwork", "thumbnail", url="https://media.test/a.jpg", extension="jpg"), SidecarSpec("nfo", "nfo", content=b"<movie/>", extension="nfo")), artwork_asset_id="artwork", metadata_tags=(("title", "Example"),))
        released = []
        execution = coordinator.execute_download_plan(value, tracker=tracker, resources=DownloadResources(), on_media_transfer_complete=lambda: released.append(tracker.snapshot()))
        assert len(calls) == 1
        assert calls[0][1]["metadata"] == {"title": "Example"}
        assert len(execution.assets) == 2
        assert (tmp_path / "library/Example.jpg").read_bytes() == b"image"
        assert (tmp_path / "library/Example.nfo").read_bytes() == b"<movie/>"
        assert released[0].primary_transfer_complete
        assert not next(stage for stage in released[0].stages if stage.id == "embed").finished_at
        assert tracker.snapshot().main_activity == "finalize"
        assert tracker.finish().phase == "complete"
        execution.cleanup_workspace()


def test_publication_collision_never_removes_identical_external_file(tmp_path):
    from dailywire_downloader.storage.publication import PublicationJournal, reconcile_publication_journal
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    media = tmp_path / "media.mp4"
    media.write_bytes(b"media")
    external = tmp_path / "media.nfo"
    external.write_bytes(b"same")
    generated = workspace / "metadata.nfo"
    generated.write_bytes(b"same")
    journal = PublicationJournal(workspace, media)
    with pytest.raises(FileExistsError):
        journal.publish(generated, ".nfo", progress=lambda _: None, should_cancel=lambda: False)
    journal.rollback()
    assert external.read_bytes() == b"same"
    assert reconcile_publication_journal(workspace, tmp_path, lambda *_: False)
    assert external.read_bytes() == b"same"


def test_library_does_not_import_application_packages():
    import ast
    import dailywire_downloader
    root = Path(dailywire_downloader.__file__).parent
    for file in root.rglob("*.py"):
        tree = ast.parse(file.read_text())
        for node in ast.walk(tree):
            names = [alias.name for alias in node.names] if isinstance(node, ast.Import) else [node.module or ""] if isinstance(node, ast.ImportFrom) else []
            assert not any(name.split(".")[0] in {"backend", "task_manager", "config"} for name in names), file


def test_required_sidecar_failure_aborts_media_and_joins_writers(tmp_path, monkeypatch):
    import time
    from dailywire_downloader import coordinator, sidecars
    from dailywire_downloader.errors import DownloadError
    media_started = Event()
    def unavailable(*_args, **_kwargs):
        assert media_started.wait(2)
        raise sidecars.InvalidSidecar('Artwork is invalid')
    monkeypatch.setattr(sidecars, 'http_get', unavailable)
    def download(_url, destination, *, progress, should_cancel):
        media_started.set()
        deadline = time.monotonic() + 2
        while not should_cancel():
            assert time.monotonic() < deadline, 'Required asset failure did not cancel media'
            time.sleep(.005)
        raise DownloadCancelled('Media stopped')
    monkeypatch.setattr(coordinator, 'download_file', download)
    with DownloadTracker() as tracker:
        value = plan(tmp_path, tracker, assets=(SidecarSpec('artwork', 'thumbnail', url='https://media.test/a.jpg'),))
        with pytest.raises(DownloadError, match='Artwork is invalid'):
            coordinator.execute_download_plan(value, tracker=tracker, resources=DownloadResources())
    assert not (tmp_path/'library/Example.mp4').exists()
    assert not list((tmp_path/'temp/.wireloft-staging').glob('attempt-*'))


def test_optional_asset_failure_preserves_successful_media(tmp_path, monkeypatch):
    from dailywire_downloader import coordinator, sidecars
    monkeypatch.setattr(sidecars, 'http_get', lambda *a, **k: (_ for _ in ()).throw(sidecars.InvalidSidecar('Invalid optional image')))
    def download(_url, destination, **_kwargs):
        Path(destination).write_bytes(b'media')
        return DownloadResult(destination, 5)
    monkeypatch.setattr(coordinator, 'download_file', download)
    with DownloadTracker() as tracker:
        value = plan(tmp_path, tracker, assets=(SidecarSpec('artwork', 'thumbnail', url='https://media.test/a.jpg', required=False),))
        execution = coordinator.execute_download_plan(value, tracker=tracker, resources=DownloadResources())
        assert not execution.assets
        assert tracker.snapshot().warnings
        assert Path(execution.result.path).read_bytes() == b'media'
        execution.cleanup_workspace()


def test_sidecar_retry_does_not_repeat_primary_transfer(tmp_path, monkeypatch):
    from dailywire_downloader import coordinator, sidecars
    attempts = []
    class Response:
        headers = {'Content-Type': 'image/jpeg', 'Content-Length': '5'}
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def iter_chunks(self, _size): yield b'image'
    def request(*_args, **_kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise OSError('Temporary network error')
        return Response()
    monkeypatch.setattr(sidecars, 'http_get', request)
    monkeypatch.setattr(sidecars, 'wait_for_retry', lambda *_: None)
    transfers = []
    def download(_url, destination, **_kwargs):
        transfers.append(1)
        Path(destination).write_bytes(b'media')
        return DownloadResult(destination, 5)
    monkeypatch.setattr(coordinator, 'download_file', download)
    with DownloadTracker() as tracker:
        value = plan(tmp_path, tracker, assets=(SidecarSpec('artwork', 'thumbnail', url='https://media.test/a.jpg'),))
        execution = coordinator.execute_download_plan(value, tracker=tracker, resources=DownloadResources())
        assert len(attempts) == 2 and len(transfers) == 1
        assert Path(execution.assets[0].path).read_bytes() == b'image'
        execution.cleanup_workspace()
