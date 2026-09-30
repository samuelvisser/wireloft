from pathlib import Path

import pytest

from dailywire_downloader.storage.relocation import PathMove, RelocationTransaction


def test_arbitrary_subtitle_suffix_relocates_and_rolls_back_with_media(tmp_path):
    source, target = tmp_path/'Movie.mp4', tmp_path/'Renamed.mp4'
    subtitle, renamed = tmp_path/'Movie.en.srt', tmp_path/'Renamed.en.srt'
    source.write_bytes(b'media'); subtitle.write_text('1\nSubtitle')
    transaction = RelocationTransaction((PathMove(source, target), PathMove(subtitle, renamed)))
    transaction.execute()
    assert target.read_bytes() == b'media'
    assert renamed.read_text() == '1\nSubtitle'
    assert not source.exists() and not subtitle.exists()
    transaction.rollback()
    assert source.read_bytes() == b'media'
    assert subtitle.read_text() == '1\nSubtitle'
    assert not target.exists() and not renamed.exists()


def test_relocation_cycles_never_overwrite(tmp_path):
    first, second = tmp_path/'one.mp4', tmp_path/'two.mp4'
    first.write_bytes(b'one'); second.write_bytes(b'two')
    transaction = RelocationTransaction((PathMove(first, second), PathMove(second, first)))
    transaction.execute()
    assert first.read_bytes() == b'two' and second.read_bytes() == b'one'
    transaction.rollback()
    assert first.read_bytes() == b'one' and second.read_bytes() == b'two'


def test_external_collision_keeps_all_sources(tmp_path):
    source, destination = tmp_path/'Movie.en.srt', tmp_path/'External.en.srt'
    source.write_bytes(b'managed'); destination.write_bytes(b'external')
    transaction = RelocationTransaction((PathMove(source, destination),))
    with pytest.raises(FileExistsError):
        transaction.execute()
    assert source.read_bytes() == b'managed'
    assert destination.read_bytes() == b'external'
