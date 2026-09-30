from pathlib import Path

import logging

from backend.services import download_relocation as service
from dailywire_downloader.storage.relocation import PathMove


def _move(download_id: int, source: Path, destination: Path):
    return service.DownloadRelocation(download_id, source, destination, (PathMove(source, destination),), ())


def test_existing_destination_is_skipped_with_warning(tmp_path, caplog):
    source = tmp_path / "source.m4a"
    destination = tmp_path / "destination.m4a"
    source.write_bytes(b"source")
    destination.write_bytes(b"existing")

    with caplog.at_level(logging.WARNING):
        remaining, skipped = service.filter_relocation_conflicts([
            _move(7, source, destination),
        ])

    assert remaining == []
    assert [move.download_id for move in skipped] == [7]
    assert "destination already exists" in caplog.text
    assert str(source) in caplog.text
    assert str(destination) in caplog.text


def test_skipping_a_move_also_skips_moves_that_need_its_source_to_vacate(tmp_path, caplog):
    first = tmp_path / "first.m4a"
    second = tmp_path / "second.m4a"
    occupied = tmp_path / "occupied.m4a"
    first.write_bytes(b"first")
    second.write_bytes(b"second")
    occupied.write_bytes(b"occupied")

    moves = [
        _move(1, first, second),
        _move(2, second, occupied),
    ]
    with caplog.at_level(logging.WARNING):
        remaining, skipped = service.filter_relocation_conflicts(moves)

    assert remaining == []
    assert {move.download_id for move in skipped} == {1, 2}


def test_internal_rename_cycle_is_not_treated_as_existing_destination_conflict(tmp_path):
    first = tmp_path / "first.m4a"
    second = tmp_path / "second.m4a"
    first.write_bytes(b"first")
    second.write_bytes(b"second")

    moves = [
        _move(1, first, second),
        _move(2, second, first),
    ]
    remaining, skipped = service.filter_relocation_conflicts(moves)

    assert remaining == moves
    assert skipped == []
