from __future__ import annotations

from types import SimpleNamespace


def test_file_watcher_ignores_artifacts_from_another_download_root(tmp_path, monkeypatch, caplog):
    from config import get_settings
    from task_manager.tasks.workers.file_watcher._helpers import _filter_current_download_root

    current_root = tmp_path / "current-downloads"
    current_root.mkdir()
    foreign_root = tmp_path / "other-host" / "downloads"

    monkeypatch.setattr(get_settings().download_settings, "download_root", current_root)

    current = SimpleNamespace(file_path=str(current_root / "shows" / "episode.m4a"))
    foreign = SimpleNamespace(file_path=str(foreign_root / "shows" / "episode.m4a"))

    assert _filter_current_download_root([current, foreign]) == [current]
    assert "skipped 1 artifact(s)" in caplog.text
    assert "outside the configured download root" in caplog.text


def test_file_watcher_preserves_artifacts_when_configured_root_is_unavailable(tmp_path, monkeypatch, caplog):
    from config import get_settings
    from task_manager.tasks.workers.file_watcher._helpers import _filter_current_download_root

    unavailable_root = tmp_path / "not-mounted"
    monkeypatch.setattr(get_settings().download_settings, "download_root", unavailable_root)

    recorded = SimpleNamespace(file_path=str(unavailable_root / "shows" / "episode.m4a"))

    assert _filter_current_download_root([recorded]) == []
    assert "configured download root" in caplog.text
    assert "is unavailable" in caplog.text
    assert "left their database state unchanged" in caplog.text
