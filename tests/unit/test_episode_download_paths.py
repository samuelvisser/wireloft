from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor


def test_reserve_unique_download_path_numbers_existing_exact_filename(tmp_path):
    from backend.utils.download_paths import reserve_unique_download_path

    requested = tmp_path / "Same title.m4a"
    requested.write_bytes(b"external file")

    reservation = reserve_unique_download_path(requested)
    try:
        assert reservation.path == tmp_path / "Same title-1.m4a"
        assert reservation.path.is_file()
        assert reservation.path.stat().st_size == 0
        assert requested.read_bytes() == b"external file"
    finally:
        reservation.release_if_unclaimed()


def test_reserve_unique_download_path_treats_extensions_as_distinct(tmp_path):
    from backend.utils.download_paths import reserve_unique_download_path

    (tmp_path / "Same title.mp4").write_bytes(b"video")

    reservation = reserve_unique_download_path(tmp_path / "Same title.m4a")
    try:
        assert reservation.path == tmp_path / "Same title.m4a"
    finally:
        reservation.release_if_unclaimed()


def test_reserve_unique_download_path_is_atomic_between_concurrent_workers(tmp_path):
    from backend.utils.download_paths import reserve_unique_download_path

    requested = tmp_path / "Same title.m4a"

    with ThreadPoolExecutor(max_workers=6) as executor:
        reservations = list(
            executor.map(
                lambda _index: reserve_unique_download_path(requested),
                range(6),
            )
        )

    try:
        assert {reservation.path.name for reservation in reservations} == {
            "Same title.m4a",
            "Same title-1.m4a",
            "Same title-2.m4a",
            "Same title-3.m4a",
            "Same title-4.m4a",
            "Same title-5.m4a",
        }
    finally:
        for reservation in reservations:
            reservation.release_if_unclaimed()


def test_release_if_unclaimed_removes_only_its_empty_placeholder(tmp_path):
    from backend.utils.download_paths import reserve_unique_download_path

    reservation = reserve_unique_download_path(tmp_path / "Same title.m4a")
    path = reservation.path
    assert path.exists()

    reservation.release_if_unclaimed()

    assert not path.exists()


def test_release_if_unclaimed_keeps_file_that_replaced_reservation(tmp_path):
    from backend.utils.download_paths import reserve_unique_download_path

    reservation = reserve_unique_download_path(tmp_path / "Same title.m4a")
    completed = tmp_path / "completed.part"
    completed.write_bytes(b"downloaded media")
    os.replace(completed, reservation.path)

    reservation.release_if_unclaimed()

    assert reservation.path.read_bytes() == b"downloaded media"
