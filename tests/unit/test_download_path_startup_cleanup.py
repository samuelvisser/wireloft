from __future__ import annotations

import asyncio
import os


def test_startup_cleanup_removes_abandoned_placeholder(tmp_path):
    from backend.utils.download_paths import (
        cleanup_abandoned_download_path_reservations,
        reserve_unique_download_path,
    )

    reservation = reserve_unique_download_path(tmp_path / "Same title.m4a")
    path = reservation.path
    marker_path = reservation.marker_path

    # Simulate an unclean shutdown by intentionally not releasing the claim.
    assert cleanup_abandoned_download_path_reservations(tmp_path) == 1

    assert not path.exists()
    assert not marker_path.exists()


def test_startup_cleanup_preserves_unmarked_zero_byte_files(tmp_path):
    from backend.utils.download_paths import cleanup_abandoned_download_path_reservations

    external = tmp_path / "External empty file.m4a"
    external.touch()

    assert cleanup_abandoned_download_path_reservations(tmp_path) == 0
    assert external.exists()
    assert external.stat().st_size == 0


def test_startup_cleanup_preserves_completed_file_if_marker_was_not_released(tmp_path):
    from backend.utils.download_paths import (
        cleanup_abandoned_download_path_reservations,
        reserve_unique_download_path,
    )

    reservation = reserve_unique_download_path(tmp_path / "Same title.m4a")
    completed = tmp_path / "completed.part"
    completed.write_bytes(b"downloaded media")
    os.replace(completed, reservation.path)

    # Simulate a kill after the atomic final rename but before the worker's
    # finally block could remove the reservation marker.
    assert cleanup_abandoned_download_path_reservations(tmp_path) == 1

    assert reservation.path.read_bytes() == b"downloaded media"
    assert not reservation.marker_path.exists()


def test_startup_cleanup_removes_abandoned_temporary_workspace(tmp_path):
    from backend.utils.download_paths import (
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
        is_published_artifact=lambda *_args: False,
    ) == 1
    assert not workspace.workspace.exists()
    assert not destination.exists()


def test_startup_cleanup_removes_published_file_not_committed_to_database(tmp_path):
    from backend.utils.download_paths import (
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

    assert published.read_bytes() == b"complete media"
    assert workspace.path.exists()
    assert cleanup_abandoned_temporary_downloads(
        temporary_root,
        download_root,
        is_published_artifact=lambda *_args: False,
    ) == 1

    assert not published.exists()
    assert not workspace.workspace.exists()


def test_startup_cleanup_preserves_published_file_committed_to_database(tmp_path):
    from backend.utils.download_paths import (
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
    identity = published.stat()

    def is_published(path, stat_dev, stat_ino):
        return (
            path == published
            and stat_dev == identity.st_dev
            and stat_ino == identity.st_ino
        )

    assert cleanup_abandoned_temporary_downloads(
        temporary_root,
        download_root,
        is_published_artifact=is_published,
    ) == 1

    assert published.read_bytes() == b"complete media"
    assert not workspace.workspace.exists()


def test_application_lifespan_cleans_download_state_before_controller_recovery(monkeypatch):
    import controller
    import backend.utils.download_paths as download_paths
    from backend.app import application_lifespan

    calls: list[str] = []
    monkeypatch.setattr(
        download_paths,
        "cleanup_abandoned_download_path_reservations",
        lambda _root: calls.append("reservation-cleanup") or 0,
    )
    monkeypatch.setattr(
        download_paths,
        "cleanup_abandoned_temporary_downloads",
        lambda *_args, **_kwargs: calls.append("temporary-cleanup") or 0,
    )
    monkeypatch.setattr(controller, "start_controller", lambda: calls.append("start"))
    monkeypatch.setattr(controller, "stop_controller", lambda: calls.append("stop"))

    async def run_lifespan():
        async with application_lifespan(None):
            calls.append("running")

    asyncio.run(run_lifespan())

    assert calls == [
        "reservation-cleanup",
        "temporary-cleanup",
        "start",
        "running",
        "stop",
    ]


def test_startup_cleanup_removes_partial_marker_without_touching_external_empty_file(tmp_path):
    from backend.utils.download_paths import (
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
