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


def test_application_lifespan_cleans_reservations_before_controller_recovery(monkeypatch):
    import controller
    import backend.utils.download_paths as download_paths
    from backend.app import application_lifespan

    calls: list[str] = []
    monkeypatch.setattr(
        download_paths,
        "cleanup_abandoned_download_path_reservations",
        lambda _root: calls.append("cleanup") or 0,
    )
    monkeypatch.setattr(controller, "start_controller", lambda: calls.append("start"))
    monkeypatch.setattr(controller, "stop_controller", lambda: calls.append("stop"))

    async def run_lifespan():
        async with application_lifespan(None):
            calls.append("running")

    asyncio.run(run_lifespan())

    assert calls == ["cleanup", "start", "running", "stop"]


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
