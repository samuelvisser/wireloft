from __future__ import annotations

import asyncio
import os
import threading


def test_startup_cleanup_removes_abandoned_placeholder(tmp_path, task_database):
    from task_manager.tasks.helpers.downloads.download_paths import (
        cleanup_abandoned_download_path_reservations,
        reserve_unique_download_path,
    )
    from task_manager.tasks.helpers.downloads.recovery_journal import (
        DownloadPathClaimType,
        list_download_path_claims,
    )

    reservation = reserve_unique_download_path(tmp_path / "Same title.m4a")
    path = reservation.path
    marker_path = reservation.marker_path

    assert len(list_download_path_claims(DownloadPathClaimType.DIRECT_RESERVATION)) == 1
    assert cleanup_abandoned_download_path_reservations(tmp_path) == 1

    assert not path.exists()
    assert not marker_path.exists()
    assert list_download_path_claims(DownloadPathClaimType.DIRECT_RESERVATION) == []


def test_startup_cleanup_discards_database_claim_when_marker_was_never_created(
    tmp_path,
    task_database,
):
    from task_manager.tasks.helpers.downloads.download_paths import (
        cleanup_abandoned_download_path_reservations,
    )
    from task_manager.tasks.helpers.downloads.recovery_journal import (
        DownloadPathClaimType,
        create_download_path_claim,
        list_download_path_claims,
    )

    candidate = tmp_path / "Never created.m4a"
    record = create_download_path_claim(
        DownloadPathClaimType.DIRECT_RESERVATION,
        candidate,
    )
    assert record is not None
    assert candidate.parent.exists()

    assert cleanup_abandoned_download_path_reservations(tmp_path) == 1
    assert list_download_path_claims(DownloadPathClaimType.DIRECT_RESERVATION) == []


def test_startup_cleanup_preserves_claim_when_download_root_is_unavailable(
    tmp_path,
    task_database,
):
    from task_manager.tasks.helpers.downloads.download_paths import (
        cleanup_abandoned_download_path_reservations,
    )
    from task_manager.tasks.helpers.downloads.recovery_journal import (
        DownloadPathClaimType,
        create_download_path_claim,
        list_download_path_claims,
    )

    unavailable_root = tmp_path / "not-mounted"
    candidate = unavailable_root / "Episode.m4a"
    record = create_download_path_claim(
        DownloadPathClaimType.DIRECT_RESERVATION,
        candidate,
    )
    assert record is not None

    assert cleanup_abandoned_download_path_reservations(unavailable_root) == 0
    assert list_download_path_claims(DownloadPathClaimType.DIRECT_RESERVATION) == [record]


def test_startup_cleanup_preserves_unmarked_zero_byte_files(tmp_path, task_database):
    from task_manager.tasks.helpers.downloads.download_paths import cleanup_abandoned_download_path_reservations

    external = tmp_path / "External empty file.m4a"
    external.touch()

    assert cleanup_abandoned_download_path_reservations(tmp_path) == 0
    assert external.exists()
    assert external.stat().st_size == 0


def test_startup_cleanup_preserves_completed_file_if_marker_was_not_released(
    tmp_path,
    task_database,
):
    from task_manager.tasks.helpers.downloads.download_paths import (
        cleanup_abandoned_download_path_reservations,
        reserve_unique_download_path,
    )

    reservation = reserve_unique_download_path(tmp_path / "Same title.m4a")
    completed = tmp_path / "completed.part"
    completed.write_bytes(b"downloaded media")
    os.replace(completed, reservation.path)

    assert cleanup_abandoned_download_path_reservations(tmp_path) == 1

    assert reservation.path.read_bytes() == b"downloaded media"
    assert not reservation.marker_path.exists()


def test_startup_cleanup_removes_stale_temporary_publication_lock(
    tmp_path,
    task_database,
):
    from task_manager.tasks.helpers.downloads.download_paths import (
        cleanup_abandoned_download_path_reservations,
    )
    from task_manager.tasks.helpers.downloads.mode_temp_folder_download import (
        _claim_publication_lock,
    )

    lock = _claim_publication_lock(tmp_path / "Episode.m4a")
    assert lock is not None
    assert lock.path.exists()

    assert cleanup_abandoned_download_path_reservations(tmp_path) == 1
    assert not lock.path.exists()


def test_startup_claim_cleanup_never_walks_the_download_library(
    tmp_path,
    task_database,
    monkeypatch,
):
    from task_manager.tasks.helpers.downloads.download_paths import (
        cleanup_abandoned_download_path_reservations,
        reserve_unique_download_path,
    )
    from task_manager.tasks.helpers.downloads.mode_temp_folder_download import (
        _claim_publication_lock,
    )

    reservation = reserve_unique_download_path(tmp_path / "Direct.m4a")
    lock = _claim_publication_lock(tmp_path / "Temporary.m4a")
    assert lock is not None

    def fail_walk(*_args, **_kwargs):
        raise AssertionError("startup claim cleanup must not recursively walk download_root")

    monkeypatch.setattr(os, "walk", fail_walk)

    assert cleanup_abandoned_download_path_reservations(tmp_path) == 2
    assert not reservation.marker_path.exists()
    assert not lock.path.exists()


def test_startup_cleanup_removes_abandoned_temporary_workspace(tmp_path, task_database):
    from task_manager.tasks.helpers.downloads.download_paths import (
        cleanup_abandoned_temporary_downloads,
        create_temporary_download_workspace,
    )

    temporary_root = tmp_path / "temporary"
    download_root = tmp_path / "downloads"
    destination = download_root / "Same title.m4a"
    workspace = create_temporary_download_workspace(temporary_root, destination)
    partial = workspace.path.with_name(workspace.path.name + ".part")
    partial.write_bytes(b"partial media")

    assert cleanup_abandoned_temporary_downloads(
        temporary_root,
        download_root,
    ) == 1
    assert not workspace.workspace.exists()
    assert not destination.exists()


def test_startup_cleanup_removes_published_file_not_committed_to_database(
    tmp_path,
    task_database,
    monkeypatch,
):
    import task_manager.tasks.helpers.downloads.mode_temp_folder_download as temporary_downloads
    from task_manager.tasks.helpers.downloads.download_paths import (
        cleanup_abandoned_temporary_downloads,
        create_temporary_download_workspace,
        publish_temporary_download,
    )

    temporary_root = tmp_path / "temporary"
    download_root = tmp_path / "downloads"
    destination = download_root / "Same title.m4a"
    workspace = create_temporary_download_workspace(temporary_root, destination)
    workspace.path.write_bytes(b"complete media")
    published = publish_temporary_download(workspace.path, destination)
    monkeypatch.setattr(
        temporary_downloads,
        "_is_committed_download_artifact",
        lambda *_args: False,
    )

    assert published.read_bytes() == b"complete media"
    assert cleanup_abandoned_temporary_downloads(
        temporary_root,
        download_root,
    ) == 1

    assert not published.exists()
    assert not workspace.workspace.exists()


def test_startup_cleanup_preserves_published_file_committed_to_database(
    tmp_path,
    task_database,
    monkeypatch,
):
    import task_manager.tasks.helpers.downloads.mode_temp_folder_download as temporary_downloads
    from task_manager.tasks.helpers.downloads.download_paths import (
        cleanup_abandoned_temporary_downloads,
        create_temporary_download_workspace,
        publish_temporary_download,
    )

    temporary_root = tmp_path / "temporary"
    download_root = tmp_path / "downloads"
    destination = download_root / "Same title.m4a"
    workspace = create_temporary_download_workspace(temporary_root, destination)
    workspace.path.write_bytes(b"complete media")
    published = publish_temporary_download(workspace.path, destination)

    seen = {}

    def is_published(path, identity):
        seen["fingerprint"] = identity.fingerprint
        return path == published

    monkeypatch.setattr(
        temporary_downloads,
        "_is_committed_download_artifact",
        is_published,
    )

    assert cleanup_abandoned_temporary_downloads(
        temporary_root,
        download_root,
    ) == 1

    assert seen["fingerprint"]
    assert published.read_bytes() == b"complete media"
    assert not workspace.workspace.exists()


def test_application_lifespan_is_ready_while_download_recovery_runs(monkeypatch):
    import controller
    import task_manager.scheduler.scheduler as scheduler_module
    import task_manager.tasks.helpers.downloads.download_paths as download_paths
    from backend.app import application_lifespan
    from config import get_settings

    calls: list[str] = []
    cleanup_started = threading.Event()
    allow_cleanup_to_finish = threading.Event()
    cleanup_finished = threading.Event()

    class FakeScheduler:
        running = True

        def pause(self):
            calls.append("pause")

        def resume(self):
            calls.append("resume")

    scheduler = FakeScheduler()

    def clean_reservations(_root):
        calls.append("reservation-cleanup")
        cleanup_started.set()
        assert allow_cleanup_to_finish.wait(timeout=2)
        return 2

    def clean_temporary(*_args, **_kwargs):
        calls.append("temporary-cleanup")
        cleanup_finished.set()
        return 3

    monkeypatch.setattr(get_settings().scheduler, "enabled", True)
    monkeypatch.setattr(scheduler_module, "start_scheduler", lambda: scheduler)
    monkeypatch.setattr(
        download_paths,
        "cleanup_abandoned_download_path_reservations",
        clean_reservations,
    )
    monkeypatch.setattr(
        download_paths,
        "cleanup_abandoned_temporary_downloads",
        clean_temporary,
    )
    monkeypatch.setattr(controller, "start_controller", lambda: calls.append("start"))
    monkeypatch.setattr(controller, "stop_controller", lambda: calls.append("stop"))

    async def run_lifespan():
        async with application_lifespan(None):
            calls.append("running")
            assert await asyncio.to_thread(cleanup_started.wait, 1)
            assert "temporary-cleanup" not in calls
            assert "resume" not in calls

            allow_cleanup_to_finish.set()
            assert await asyncio.to_thread(cleanup_finished.wait, 1)
            for _ in range(100):
                if "resume" in calls:
                    break
                await asyncio.sleep(0.001)
            assert "resume" in calls

    asyncio.run(run_lifespan())

    assert calls.index("pause") < calls.index("start")
    assert calls.index("start") < calls.index("running")
    assert calls.index("running") < calls.index("temporary-cleanup")
    assert calls.index("reservation-cleanup") < calls.index("temporary-cleanup")
    assert calls.index("temporary-cleanup") < calls.index("resume")
    assert calls.index("resume") < calls.index("stop")


def test_startup_cleanup_removes_partial_marker_without_touching_external_empty_file(
    tmp_path,
    task_database,
):
    from task_manager.tasks.helpers.downloads.download_paths import (
        cleanup_abandoned_download_path_reservations,
        reserve_unique_download_path,
    )

    reservation = reserve_unique_download_path(tmp_path / "Same title.m4a")
    reservation.path.unlink()
    reservation.marker_path.write_bytes(b"WIRELOFT_DOWNLOAD_PATH")
    external = tmp_path / "External empty file.m4a"
    external.touch()

    assert cleanup_abandoned_download_path_reservations(tmp_path) == 1

    assert not reservation.marker_path.exists()
    assert external.exists()
