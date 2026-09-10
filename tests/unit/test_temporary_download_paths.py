from __future__ import annotations

import errno
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest


def test_temporary_download_is_not_visible_at_destination_until_publish(tmp_path):
    from backend.utils.download_paths import (
        create_temporary_download_workspace,
        publish_temporary_download,
    )

    temporary_root = tmp_path / "temporary"
    destination = tmp_path / "downloads" / "Episode.m4a"
    workspace = create_temporary_download_workspace(temporary_root, destination)
    try:
        workspace.path.write_bytes(b"complete media")

        assert workspace.path.exists()
        assert not destination.exists()
        assert not destination.parent.exists()

        published = publish_temporary_download(workspace.path, destination)

        assert published == destination
        assert destination.read_bytes() == b"complete media"
        # The private hard link remains until the database commits the artifact;
        # normal worker cleanup removes the whole workspace immediately after.
        assert workspace.path.exists()
        assert workspace.path.stat().st_ino == destination.stat().st_ino
    finally:
        workspace.cleanup()

    assert not workspace.path.exists()
    assert destination.read_bytes() == b"complete media"


def test_temporary_publish_numbers_existing_exact_filename(tmp_path):
    from backend.utils.download_paths import (
        create_temporary_download_workspace,
        publish_temporary_download,
    )

    temporary_root = tmp_path / "temporary"
    destination = tmp_path / "downloads" / "Episode.m4a"
    destination.parent.mkdir(parents=True)
    destination.write_bytes(b"external media")

    workspace = create_temporary_download_workspace(temporary_root, destination)
    try:
        workspace.path.write_bytes(b"new media")
        published = publish_temporary_download(workspace.path, destination)

        assert published == destination.parent / "Episode-1.m4a"
        assert destination.read_bytes() == b"external media"
        assert published.read_bytes() == b"new media"
    finally:
        workspace.cleanup()


def test_temporary_publish_treats_extensions_as_distinct(tmp_path):
    from backend.utils.download_paths import (
        create_temporary_download_workspace,
        publish_temporary_download,
    )

    downloads = tmp_path / "downloads"
    downloads.mkdir()
    (downloads / "Episode.mp4").write_bytes(b"video")
    destination = downloads / "Episode.m4a"

    workspace = create_temporary_download_workspace(tmp_path / "temporary", destination)
    try:
        workspace.path.write_bytes(b"audio")
        assert publish_temporary_download(workspace.path, destination) == destination
    finally:
        workspace.cleanup()


def test_temporary_publish_is_atomic_between_concurrent_workers(tmp_path):
    from backend.utils.download_paths import (
        create_temporary_download_workspace,
        publish_temporary_download,
    )

    destination = tmp_path / "downloads" / "Episode.m4a"
    workspaces = [
        create_temporary_download_workspace(tmp_path / "temporary", destination)
        for _ in range(6)
    ]
    for index, workspace in enumerate(workspaces):
        workspace.path.write_bytes(f"media-{index}".encode())

    try:
        with ThreadPoolExecutor(max_workers=6) as executor:
            published = list(executor.map(
                lambda workspace: publish_temporary_download(workspace.path, destination),
                workspaces,
            ))

        assert {path.name for path in published} == {
            "Episode.m4a",
            "Episode-1.m4a",
            "Episode-2.m4a",
            "Episode-3.m4a",
            "Episode-4.m4a",
            "Episode-5.m4a",
        }
        assert {path.read_bytes() for path in published} == {
            b"media-0",
            b"media-1",
            b"media-2",
            b"media-3",
            b"media-4",
            b"media-5",
        }
    finally:
        for workspace in workspaces:
            workspace.cleanup()


def test_temporary_publish_rejects_cross_filesystem_publish(tmp_path, monkeypatch):
    import backend.utils.download_paths as download_paths

    destination = tmp_path / "downloads" / "Episode.m4a"
    workspace = download_paths.create_temporary_download_workspace(
        tmp_path / "temporary",
        destination,
    )
    workspace.path.write_bytes(b"complete media")

    def cross_device_link(_source, _destination):
        raise OSError(errno.EXDEV, "cross-device link")

    monkeypatch.setattr(download_paths.os, "link", cross_device_link)
    try:
        with pytest.raises(
            download_paths.TemporaryDownloadFilesystemError,
            match="same filesystem or volume",
        ):
            download_paths.publish_temporary_download(workspace.path, destination)
        assert not destination.exists()
        assert workspace.path.read_bytes() == b"complete media"
    finally:
        workspace.cleanup()


def test_episode_download_profile_mode_resolves_against_system_default(monkeypatch):
    from config import get_settings
    from config.settings.submodels import DownloadMode
    from task_manager.tasks.workers.download_episode.service import _effective_download_mode

    settings = get_settings().download_settings
    monkeypatch.setattr(settings, "download_mode", DownloadMode.TEMPORARY)

    inherited = SimpleNamespace(
        download_profile=SimpleNamespace(download_mode="system")
    )
    forced_direct = SimpleNamespace(
        download_profile=SimpleNamespace(download_mode="direct")
    )
    forced_temporary = SimpleNamespace(
        download_profile=SimpleNamespace(download_mode="temporary")
    )
    manual_download = SimpleNamespace(download_profile=None)

    assert _effective_download_mode(inherited) is DownloadMode.TEMPORARY
    assert _effective_download_mode(forced_direct) is DownloadMode.DIRECT
    assert _effective_download_mode(forced_temporary) is DownloadMode.TEMPORARY
    assert _effective_download_mode(manual_download) is DownloadMode.TEMPORARY


def test_episode_attempt_keeps_destination_absent_until_temporary_download_finishes(tmp_path, monkeypatch):
    from config import get_settings
    from config.settings.submodels import DownloadMode
    from dailywire_downloader import DownloadResult, MediaInfo, MediaKind
    from task_manager.tasks.workers.download_episode import service

    settings = get_settings().download_settings
    temporary_root = tmp_path / "temporary"
    destination = tmp_path / "downloads" / "Episode.m4a"
    monkeypatch.setattr(settings, "download_mode", DownloadMode.TEMPORARY)
    monkeypatch.setattr(settings, "temporary_download_root", temporary_root)
    monkeypatch.setattr(settings, "remux_video_to_mp4", False)
    monkeypatch.setattr(
        service,
        "resolve_episode_output_path",
        lambda *_args, **_kwargs: destination,
    )
    monkeypatch.setattr(
        service,
        "probe",
        lambda _url: MediaInfo(
            url="https://example.test/audio.m4a",
            kind=MediaKind.DIRECT_FILE,
            content_type="audio/mp4",
        ),
    )

    pending_path = "/downloads/pending.ext"
    download = SimpleNamespace(
        local_media_profile=SimpleNamespace(
            output_template="/downloads/{{ episode }}.ext",
            preferred_format="format_audio_only",
        ),
        download_profile=SimpleNamespace(download_mode="system"),
        file_path=pending_path,
    )
    observed: dict[str, object] = {}

    def fake_download_file(_url, dest_path, *, progress=None, should_cancel=None):
        from pathlib import Path

        staged = Path(dest_path)
        observed["staged"] = staged
        assert not destination.exists()
        assert download.file_path == pending_path
        assert temporary_root in staged.parents
        staged.parent.mkdir(parents=True, exist_ok=True)
        staged.write_bytes(b"complete media")
        return DownloadResult(path=str(staged), bytes_downloaded=14)

    monkeypatch.setattr(service, "download_file", fake_download_file)

    class FakeSession:
        commits = 0

        def commit(self):
            self.commits += 1

    session = FakeSession()
    owned_paths: list[str] = []
    temporary_workspaces = []
    result = service._attempt_download(
        session,
        download=download,
        episode=SimpleNamespace(),
        url="https://example.test/audio.m4a",
        want_audio=True,
        task_progress=None,
        cancellation=None,
        owned_paths=owned_paths,
        temporary_workspaces=temporary_workspaces,
    )

    try:
        assert result.file_path == str(destination)
        assert destination.read_bytes() == b"complete media"
        # The final path is deliberately not persisted by _attempt_download;
        # run_download_episode does that together with artifact identity/status.
        assert download.file_path == pending_path
        assert owned_paths == [str(destination)]
        assert session.commits == 0
        assert observed["staged"] != destination
        assert len(temporary_workspaces) == 1
        assert temporary_workspaces[0].path.exists()
    finally:
        for workspace in temporary_workspaces:
            workspace.cleanup()
