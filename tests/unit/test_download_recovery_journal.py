from __future__ import annotations

from pathlib import Path

import pytest


def test_direct_reservation_commits_journal_before_filesystem_marker(
    tmp_path,
    task_database,
    monkeypatch,
):
    import task_manager.tasks.helpers.downloads.mode_direct_download as direct
    from task_manager.tasks.helpers.downloads.recovery_journal import (
        DownloadPathClaimType,
        list_download_path_claims,
    )

    real_open = direct.os.open
    marker_seen = False

    def guarded_open(path, flags, mode=0o777):
        nonlocal marker_seen
        if Path(path).name.startswith(direct._RESERVATION_MARKER_PREFIX):
            claims = list_download_path_claims(DownloadPathClaimType.DIRECT_RESERVATION)
            assert len(claims) == 1
            assert claims[0].candidate_path == tmp_path / "Episode.m4a"
            marker_seen = True
        return real_open(path, flags, mode)

    monkeypatch.setattr(direct.os, "open", guarded_open)
    reservation = direct.reserve_unique_download_path(tmp_path / "Episode.m4a")
    try:
        assert marker_seen
    finally:
        reservation.release_if_unclaimed()

    assert list_download_path_claims(DownloadPathClaimType.DIRECT_RESERVATION) == []


def test_publication_lock_commits_journal_before_filesystem_marker(
    tmp_path,
    task_database,
    monkeypatch,
):
    import task_manager.tasks.helpers.downloads.mode_temp_folder_download as temporary
    from task_manager.tasks.helpers.downloads.recovery_journal import (
        DownloadPathClaimType,
        list_download_path_claims,
    )

    real_open = temporary.os.open
    marker_seen = False

    def guarded_open(path, flags, mode=0o777):
        nonlocal marker_seen
        if Path(path).name.startswith(temporary._PUBLICATION_LOCK_PREFIX):
            claims = list_download_path_claims(DownloadPathClaimType.PUBLICATION_LOCK)
            assert len(claims) == 1
            assert claims[0].candidate_path == tmp_path / "Episode.m4a"
            marker_seen = True
        return real_open(path, flags, mode)

    monkeypatch.setattr(temporary.os, "open", guarded_open)
    lock = temporary._claim_publication_lock(tmp_path / "Episode.m4a")
    assert lock is not None
    try:
        assert marker_seen
    finally:
        lock.release()

    assert list_download_path_claims(DownloadPathClaimType.PUBLICATION_LOCK) == []


def test_filesystem_marker_creation_failure_removes_database_claim(
    tmp_path,
    task_database,
    monkeypatch,
):
    import task_manager.tasks.helpers.downloads.mode_direct_download as direct
    from task_manager.tasks.helpers.downloads.recovery_journal import (
        DownloadPathClaimType,
        list_download_path_claims,
    )

    real_open = direct.os.open

    def fail_marker(path, flags, mode=0o777):
        if Path(path).name.startswith(direct._RESERVATION_MARKER_PREFIX):
            raise PermissionError("marker creation failed")
        return real_open(path, flags, mode)

    monkeypatch.setattr(direct.os, "open", fail_marker)

    with pytest.raises(PermissionError, match="marker creation failed"):
        direct.reserve_unique_download_path(tmp_path / "Episode.m4a")

    assert list_download_path_claims(DownloadPathClaimType.DIRECT_RESERVATION) == []


def test_identityless_marker_never_deletes_existing_zero_byte_candidate(
    tmp_path,
    task_database,
):
    import task_manager.tasks.helpers.downloads.mode_direct_download as direct
    from task_manager.tasks.helpers.downloads.recovery_journal import (
        DownloadPathClaimType,
        create_download_path_claim,
        list_download_path_claims,
    )

    candidate = tmp_path / "External empty file.m4a"
    candidate.touch()
    record = create_download_path_claim(
        DownloadPathClaimType.DIRECT_RESERVATION,
        candidate,
    )
    assert record is not None

    marker = direct._marker_path(candidate)
    marker.write_bytes(direct._marker_payload(candidate))

    assert direct.cleanup_abandoned_direct_download_path_reservations(tmp_path) == 1
    assert candidate.exists()
    assert candidate.stat().st_size == 0
    assert not marker.exists()
    assert list_download_path_claims(DownloadPathClaimType.DIRECT_RESERVATION) == []
