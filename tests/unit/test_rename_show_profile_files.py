from pathlib import Path

import logging

from task_manager.tasks.workers.rename_show_profile_files import service


def _move(download_id: int, source: Path, destination: Path):
    return service._Move(
        download_id=download_id,
        source=source,
        destination=destination,
        thumbnail_source=None,
        thumbnail_destination=None,
    )


def test_existing_destination_is_skipped_with_warning(tmp_path, caplog):
    source = tmp_path / "source.m4a"
    destination = tmp_path / "destination.m4a"
    source.write_bytes(b"source")
    destination.write_bytes(b"existing")

    with caplog.at_level(logging.WARNING):
        remaining, skipped = service._skip_existing_destination_conflicts([
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
        remaining, skipped = service._skip_existing_destination_conflicts(moves)

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
    remaining, skipped = service._skip_existing_destination_conflicts(moves)

    assert remaining == moves
    assert skipped == []
